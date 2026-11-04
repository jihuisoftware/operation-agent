"""Stable evidence batches reuse validated work across insertion, days and legacy checkpoints."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json

from plugins.operations import analytics, industry, topics
from plugins.operations.analysis_config import settings
from plugins.operations.policy import DEFAULT
from plugins.operations.store import Store
from tests.plugins.operations_support import prepare_materials


def configured(tmp_path, monkeypatch, count=45):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store(tmp_path / 'cache.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='增量分析', goal='只处理新增证据')
    policy['modules'].update(organize=True, analytics=True, industry=True, topics=True)
    store.configure(policy, 0)
    day = '2026-11-04'
    for i in range(count):
        add_source(store, policy, day, f'source-{i:03}')
    if count:
        prepare_materials(store, policy, day, monkeypatch)
    return store, policy, day


def add_source(store, policy, day, identity):
    store.put('source', {'day': day, 'scope_topic': policy['topic'], 'title': identity,
                        'url': f'https://example.org/{identity}', 'text': f'完整正文 {identity}', 'state': 'read'}, identity)


def finding(rows):
    return {'view': 'content', 'dimension': '需求', 'title': '样本结论', 'text': '文档提供的方法',
            'evidence_ids': [rows[0]['id']], 'scope': '仅当前所列资料', 'counter': '尚无反证', 'unknowns': '效果待验证', 'visibility': 'public'}


def test_inserted_source_and_next_day_reuse_completed_batch_members(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(industry, 'generate', lambda *args: calls.append(args[-1]) or {'findings': [finding(args[-1]['evidence'])]})
    analytics.analyze(store, policy, day, 1)
    industry.analyze(store, policy, day, 1)
    assert len(calls) == 3
    add_source(store, policy, day, '000-insert-before-existing')
    prepare_materials(store, policy, day, monkeypatch)
    analytics.analyze(store, policy, day, 1)
    industry.analyze(store, policy, day, 1)
    assert len(calls) == 4 and len(calls[-1]['evidence']) == 1
    tomorrow = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    analytics.analyze(store, policy, tomorrow, 1)
    industry.analyze(store, policy, tomorrow, 1)
    assert len(calls) == 4
    assert store.objects('industry_report')[0]['reused'] == 46


def test_quick_analysis_reuses_results_and_only_adds_one_batch(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(industry, 'generate', lambda *args: calls.append(args[-1]) or {'findings': [finding(args[-1]['evidence'])]})
    store.run_options = {'quick': True}
    analytics.analyze(store, policy, day, 1)
    industry.analyze(store, policy, day, 1)
    first = store.objects('industry_report')[0]
    assert len(calls) == 1 and first['pending'] == 25
    industry.analyze(store, policy, day, 1)
    second = store.objects('industry_report')[0]
    assert len(calls) == 2 and second['reused'] == 20 and second['pending'] == 5


def test_verified_legacy_checkpoint_migrates_without_regenerating(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, monkeypatch, count=2)
    analytics.analyze(store, policy, day, 1)
    report = store.objects('analytics_report')[0]
    rows = sorted(report['evidence'], key=lambda row: row['id'])
    config = settings(store)
    data = {'task': 'industry_analysis', 'topic': policy['topic'],
            **{key: config['config'][key] for key in ('industry', 'region', 'focus')},
            'window': report['window'], 'visibility': 'public', 'evidence': rows}
    digest = hashlib.sha256(json.dumps({'instruction': industry.INSTRUCTION, 'input': data,
        'config_version': report['config_version'], 'datasets': report['datasets']}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    result = finding(rows)
    store.put('industry_batch', {'day': day, 'findings': [result], 'covered_ids': [row['id'] for row in rows], 'created': '2026-11-04T01:00:00+00:00'}, 'industry-batch:' + digest)
    store.put('industry_report', {**report, 'findings': [result], 'pending': 0, 'covered_ids': [row['id'] for row in rows]})
    monkeypatch.setattr(industry, 'generate', lambda *_: (_ for _ in ()).throw(AssertionError('valid historical work must be reused')))
    tomorrow = '2026-11-05'
    analytics.analyze(store, policy, tomorrow, 1)
    industry.analyze(store, policy, tomorrow, 1)
    saved = store.objects('industry_report')[0]
    assert saved['reused'] == 2
    assert saved['findings'][0]['origin_window'] == report['window']
    assert saved['findings'][0]['analysis_origin'] == 'historical'


def test_topic_exact_input_reuses_but_explicit_force_regenerates(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, monkeypatch, count=1)
    policy['modules'].update(analytics=False, industry=False)
    store.configure(policy, 1)
    calls = []
    monkeypatch.setattr(topics, 'generate', lambda *args: calls.append(args[-1]) or {'topics': [{'title': '有依据的题目', 'source_ids': ['source-000']}]})
    topics.generate_topics(store, policy, day, 2)
    topics.generate_topics(store, policy, day, 2)
    assert len(calls) == 1
    topics.generate_topics(store, policy, day, 2, force=True)
    assert len(calls) == 2


def test_complete_identical_source_can_map_new_id_but_partial_source_cannot(tmp_path, monkeypatch):
    from plugins.operations.analysis_config import configure
    from plugins.operations import industry_cache
    store, policy, day = configured(tmp_path, monkeypatch, count=1)
    original = store.objects('source')[0]
    configure(store, {'version': 0, 'config': {'period': '1'}})
    calls = []
    monkeypatch.setattr(industry, 'generate', lambda *args: calls.append(args[-1]) or {'findings': [finding(args[-1]['evidence'])]})
    analytics.analyze(store, policy, day, 1)
    industry.analyze(store, policy, day, 1)
    tomorrow = '2026-11-05'
    alias = {**original, 'day': tomorrow}
    alias.pop('id', None)
    store.put('source', alias, 'same-source-new-id')
    prepare_materials(store, policy, tomorrow, monkeypatch)
    analytics.analyze(store, policy, tomorrow, 1)
    industry.analyze(store, policy, tomorrow, 1)
    assert len(calls) == 1
    report = store.objects('industry_report')[0]
    assert report['findings'][0]['evidence_ids'] == ['same-source-new-id']
    partial = {**report['evidence'][0], 'source_complete': False}
    industry_cache.save(store, 'partial-test', [partial], [finding([partial])], report)
    changed_id = {**partial, 'id': 'another-id'}
    reused, covered, pending = industry_cache.reusable(store, 'partial-test', [changed_id], report)
    assert not reused and not covered and pending == [changed_id]


def test_explicit_topic_requests_are_idempotent_and_respect_existing_lease(tmp_path, monkeypatch):
    import pytest
    from plugins.operations import topic_runs
    from plugins.operations.policy import local_day
    store, policy, _ = configured(tmp_path, monkeypatch, count=0)
    day = local_day(policy)
    add_source(store, policy, day, 'source-000')
    prepare_materials(store, policy, day, monkeypatch)
    calls = []
    monkeypatch.setattr(topics, 'generate', lambda *args: calls.append(args[-1]) or {'topics': [{'title': '选题', 'source_ids': ['source-000']}]})
    body = {'version': 1, 'request_id': 'one-request', 'force': True}
    assert store.lease('scheduled')
    with pytest.raises(ValueError, match='未启动'):
        topic_runs.run(store, body)
    assert not calls
    store.release('scheduled')
    result = topic_runs.run(store, body)
    assert result['state'] == 'completed' and len(calls) == 1
    assert topic_runs.run(store, body) == result and len(calls) == 1
    with pytest.raises(ValueError, match='同一请求'):
        topic_runs.run(store, {**body, 'force': False})


def test_window_exit_and_semantic_configuration_change_invalidate_only_valid_cohorts(tmp_path, monkeypatch):
    from plugins.operations import analysis_config
    from plugins.operations.collection_ledger import save
    store, policy, day = configured(tmp_path, monkeypatch, count=2)
    earlier = next(row for row in store.objects('source') if row['id'] == 'source-000')
    save(store, 'source', earlier['id'], {**earlier, 'day': '2026-11-03'})
    analysis_config.configure(store, {'version': 0, 'config': {'period': 'custom', 'start': '2026-11-03', 'end': day}})
    calls = []
    monkeypatch.setattr(industry, 'generate', lambda *args: calls.append(args[-1]) or {'findings': [finding(args[-1]['evidence'])]})
    analytics.analyze(store, policy, day, 1)
    industry.analyze(store, policy, day, 1)
    assert len(calls) == 1
    analysis_config.configure(store, {'version': 1, 'config': {'period': 'custom', 'start': day, 'end': day}})
    analytics.analyze(store, policy, day, 1)
    industry.analyze(store, policy, day, 1)
    saved = store.objects('industry_report')[0]
    assert len(calls) == 2 and saved['reused'] == 0
    assert {identity for item in saved['findings'] for identity in item['evidence_ids']} == {'source-001'}
    analysis_config.configure(store, {'version': 2, 'config': {'period': 'custom', 'start': day, 'end': day, 'focus': ['安全']}})
    analytics.analyze(store, policy, day, 1)
    industry.analyze(store, policy, day, 1)
    assert len(calls) == 3
