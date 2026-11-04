"""A provider failure can retain verified candidates without accepting stale evidence."""
from copy import deepcopy

import pytest

from devtools import operations_debug as debug
from plugins.operations import content, topics
from plugins.operations.model_errors import ModelServiceUnavailable
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store, encoded
from tests.plugins.operations_support import prepare_materials


def setup_topics(tmp_path, monkeypatch, *, analysis=False):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('development:\n  operations_debug: true\n')
    store = Store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='步行', goal='路线资料')
    policy['modules'].update(organize=True, topics=True, content=True, analytics=analysis)
    store.configure(policy, 0)
    day = local_day(policy)
    for identity in ('one', 'two'):
        store.put('source', {'day': day, 'scope_topic': policy['topic'], 'text': identity + '路线资料',
                            'state': 'read', 'title': identity, 'url': 'https://example.org/' + identity}, identity)
    prepare_materials(store, policy, day, monkeypatch)
    if analysis:
        from plugins.operations.analytics import analyze
        analyze(store, policy, day, 1)
    monkeypatch.setattr(topics, 'generate', lambda *_: {'topics': [
        {'title': identity + '路线', 'source_ids': [identity]} for identity in ('one', 'two')]})
    topics.generate_topics(store, policy, day, 1)
    original = store.objects('brief')[0]
    def unavailable(*_):
        raise ModelServiceUnavailable('模拟选题连接超时')
    monkeypatch.setattr(topics, 'generate', unavailable)
    return store, policy, day, original


def revise(store, identities):
    with store.connection() as db:
        for source in store.objects('source'):
            if source['id'] in identities:
                source['text'] += '已修改正文'
                db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(source), source['id']))


def test_partial_candidates_feed_content_with_current_batch_lineage(tmp_path, monkeypatch):
    store, policy, day, original = setup_topics(tmp_path, monkeypatch)
    revise(store, {'two'})
    prepare_materials(store, policy, day, monkeypatch)
    seen = []
    def write(*args):
        seen.append(args[-1]['selected_topic'])
        return {'title': '步行路线', 'body': '来源支持的路线', 'source_ids': ['one'], 'asset_ids': []}
    monkeypatch.setattr(content, 'generate', write)
    monkeypatch.setattr(content, 'check_content', lambda *_: {'pass': True})
    result = debug.execute({'task': 'pipeline', 'tasks': ['topics', 'content'], 'version': 1, 'request_id': 'partial'})
    stages = {step['id']: step for step in result['steps']}
    assert stages['topics']['state'] == 'needs_attention'
    assert stages['topics']['result']['usable'] == 1
    assert '部分可用' in stages['topics']['detail'] and '超时' in stages['topics']['detail']
    assert stages['content']['state'] == 'completed'
    assert seen[0]['title'] == 'one路线'
    chosen = store.objects('content')[0]['selected_topic']
    brief = next(row for row in store.objects('brief') if row['id'] == chosen['brief_id'])
    assert brief['manual_run_id'] == result['id']
    assert brief['result']['reused_from'] == original['id']
    assert [row['title'] for row in brief['result']['topics']] == ['one路线']
    assert len(next(row for row in store.objects('brief') if row['id'] == original['id'])['result']['topics']) == 2
    assert not store.snapshot()['actions']


@pytest.mark.parametrize('invalid', ['sources', 'day', 'version', 'topic', 'organization'])
def test_no_valid_candidates_keeps_failure_and_blocks_content(tmp_path, monkeypatch, invalid):
    store, policy, day, original = setup_topics(tmp_path, monkeypatch)
    if invalid == 'sources':
        revise(store, {'one', 'two'})
        prepare_materials(store, policy, day, monkeypatch)
    elif invalid == 'organization':
        with store.connection() as db:
            for row in store.objects('organized_source'):
                row['summary'] = '已修正的整理结论'
                db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(row), row['id']))
    else:
        original[{'day': 'day', 'version': 'version', 'topic': 'scope_topic'}[invalid]] = {
            'day': '2000-01-01', 'version': 0, 'topic': '别的主题'}[invalid]
        with store.connection() as db:
            db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(original), original['id']))
    # A changed task input prevents the exact-input reuse fast path.
    store.put('task', {'day': day, 'title': '新增要求'})
    monkeypatch.setattr(content, 'generate', lambda *_: pytest.fail('没有有效选题不能生产'))
    result = debug.execute({'task': 'pipeline', 'tasks': ['topics', 'content'], 'version': 1, 'request_id': 'invalid'})
    assert [step['state'] for step in result['steps']] == ['failed', 'skipped']
    assert not store.objects('content')


def test_changed_analysis_permissions_cannot_supply_partial_topics(tmp_path, monkeypatch):
    from plugins.operations import analysis_config, analytics
    store, policy, day, _ = setup_topics(tmp_path, monkeypatch, analysis=True)
    analysis_config.configure(store, {'version': 0, 'config': {'period': '1'}})
    analytics.analyze(store, policy, day, 1)
    with pytest.raises(ModelServiceUnavailable):
        topics.generate_topics(store, policy, day, 1)
    assert len(store.objects('brief')) == 1


def test_explicit_regeneration_reports_partial_and_keeps_request_idempotency(tmp_path, monkeypatch):
    from plugins.operations.topic_runs import run
    store, _, _, _ = setup_topics(tmp_path, monkeypatch)
    body = {'version': 1, 'request_id': 'partial-regenerate', 'force': True}
    result = run(store, body)
    assert result['state'] == 'needs_attention' and '2 个有效选题' in result['detail']
    assert run(store, body) == result
    assert len(store.objects('brief')) == 2
