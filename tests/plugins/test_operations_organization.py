"""Preparation is durable, bounded and required by topic/content generation."""
from copy import deepcopy

import pytest

from plugins.operations import organization, topics, content
from plugins.operations.organization_catalog import catalog
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store
from tests.plugins.operations_support import organized_response, prepare_materials


@pytest.fixture
def configured(tmp_path):
    store = Store(tmp_path / 'data.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='收纳', goal='有出处的方法')
    policy['modules'].update(research=True, organize=True, topics=True, content=True)
    store.configure(policy, 0)
    day = local_day(policy)
    for index in range(10):
        store.put('source', {'day': day, 'scope_topic': policy['topic'], 'title': f'方法{index}',
                  'text': f'原文{index}', 'url': f'https://example.org/{index}', 'state': 'read'}, str(index))
    return store, policy, day


def test_incremental_batches_resume_and_downstream_only_receives_organized_evidence(configured, monkeypatch):
    store, policy, day = configured
    with pytest.raises(organization.StageSkipped, match='整理资料'):
        topics.generate_topics(store, policy, day, 1)
    policy['model_calls'] = 4  # One batch + three downstream calls.
    store.configure(policy, 1)
    calls = []
    def generate(*args):
        calls.append(args[-1])
        return organized_response(args[-1])
    monkeypatch.setattr(organization, 'generate', generate)
    first = organization.organize(store, policy, day, 2)
    assert first['organized'] == 4 and first['pending'] == 6
    organization.organize(Store(store.path), policy, day, 2)
    organization.organize(store, policy, day, 2)
    organization.organize(store, policy, day, 2)
    assert [len(call['sources']) for call in calls] == [4, 4, 2]
    def plan(*args):
        rows = args[-1]['sources']
        assert all('text' not in row and row['summary'] and row['organization_id'] for row in rows)
        return {'topics': [{'title': '收纳方法', 'source_ids': [row['id'] for row in rows]}]}
    monkeypatch.setattr(topics, 'generate', plan)
    topics.generate_topics(store, policy, day, 2)
    def produce(*args):
        rows = args[-1]['sources']
        assert len(rows) == 10 and rows[0]['uncertainties'] == ['尚未独立核实']
        return {'title': '收纳方法', 'body': '有出处的方法', 'source_ids': [rows[0]['id']], 'asset_ids': []}
    monkeypatch.setattr(content, 'generate', produce)
    monkeypatch.setattr(content, 'check_content', lambda *args: {'pass': True})
    content.produce_content(store, policy, day, 2)
    saved = store.objects('content')[0]
    assert saved['organization_ids'] == [saved['organized_evidence'][0]['organization_id']]
    assert store.objects('source')[0]['text'].startswith('原文')
    view = catalog(store, category='方法教程')
    assert view['organized'] == view['matching'] == 10 and view['pending'] == 0


def test_invalid_references_fail_atomically_and_changed_source_or_topic_cannot_reuse(configured, monkeypatch):
    store, policy, day = configured
    monkeypatch.setattr(organization, 'generate', lambda *args: {'items': [{'source_id': 'foreign'}] * 4})
    with pytest.raises(ValueError, match='未知'):
        organization.organize(store, policy, day, 1)
    assert not store.objects('organized_source')
    prepare_materials(store, policy, day, monkeypatch)
    with store.connection() as db:
        db.execute("UPDATE objects SET data=json_set(data,'$.text','更新后的原文') WHERE id='0'")
    assert catalog(store)['pending'] == 1
    store.configure({**policy, 'topic': '另一主题'}, 1)
    assert catalog(store)['organized'] == 0
    assert Store(store.path.parent / 'other.db').objects('organized_source') == []




def test_zero_budget_and_next_day_resume_keep_unfinished_sources_visible(configured, monkeypatch):
    from datetime import date, timedelta
    store, policy, day = configured
    policy['model_calls'] = 0
    store.configure(policy, 1)
    monkeypatch.setattr(organization, 'generate', lambda *args: pytest.fail('零额度不能调用模型'))
    outcome = organization.organize(store, policy, day, 2)
    assert outcome['pending'] == 10 and outcome['organized'] == 0
    policy['model_calls'] = 10
    store.configure(policy, 2)
    tomorrow = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    prepare_materials(store, policy, tomorrow, monkeypatch)
    assert len(store.objects('organized_source')) == 10
    # Historical organization does not silently authorize cross-day production.
    with pytest.raises(organization.StageSkipped):
        organization.production_evidence(store, policy, tomorrow)
    from plugins.operations.source_library import reuse
    reuse(store, '0', {'version': 3, 'enabled': True})
    sources, evidence = organization.production_evidence(store, policy, tomorrow)
    assert [s['id'] for s in sources] == ['0']
    assert evidence[0]['organization_id'] in {r['id'] for r in store.objects('organized_source')}


def test_partial_response_saves_valid_rows_and_only_retries_missing_within_budget(configured, monkeypatch):
    store, policy, day = configured
    policy['model_calls'] = 5  # Two preparation calls; three reserved for downstream.
    store.configure(policy, 1)
    calls = []
    omitted = []
    def generate(*args):
        data = args[-1]
        calls.append([s['id'] for s in data['sources']])
        result = organized_response(data)
        if len(calls) == 1:
            omitted.extend(row['source_id'] for row in result['items'][2:])
            result['items'] = result['items'][:2]
        return result
    monkeypatch.setattr(organization, 'generate', generate)
    result = organization.organize(store, policy, day, 2)
    assert result['added'] == result['organized'] == 3 and result['pending'] == 7
    assert len(calls) == 2 and calls[1] == omitted[:1]
    saved_ids = {row['source_id'] for row in Store(store.path).objects('organized_source')}
    assert saved_ids == set(calls[0][:2] + calls[1])
    with store.connection() as db:
        import json
        event = json.loads(db.execute("SELECT data FROM events WHERE kind='organization_batch' ORDER BY id LIMIT 1").fetchone()[0])
    assert event['requested'] == calls[0] and event['missing'] == omitted
    calls.clear()
    monkeypatch.setattr(organization, 'generate', lambda *args: calls.append([s['id'] for s in args[-1]['sources']]) or organized_response(args[-1]))
    result = organization.organize(Store(store.path), policy, day, 2)
    assert result['pending'] == 0 and result['added'] == 7
    assert not saved_ids.intersection(s for batch in calls for s in batch)


@pytest.mark.parametrize('response', [{'items': []}, {}])
def test_empty_responses_stop_after_one_retry_per_source_and_remain_pending(configured, monkeypatch, response):
    store, policy, day = configured
    calls = []
    monkeypatch.setattr(organization, 'generate', lambda *args: calls.append([s['id'] for s in args[-1]['sources']]) or response)
    result = organization.organize(store, policy, day, 1)
    assert result['organized'] == result['added'] == 0 and result['pending'] == 10
    assert len(calls) == 13  # Three original batches and ten individual retries.
    assert '未返回' in result['detail']
    assert '额度已用完' not in result['detail']
    from plugins.operations.outcomes import describe
    assert describe('organize', result)[0] == 'needs_attention'
