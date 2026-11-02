"""Quick start uses real profile storage and Cron with mocked network boundaries."""
from copy import deepcopy
from datetime import datetime, timedelta, UTC
import json

import pytest

from plugins.operations import blueprints, collection, occurrences, quick_start, readiness, runtime, workflow
from plugins.operations.collection_ledger import load
from plugins.operations.policy import DEFAULT
from plugins.operations.store import Store


def body(store, identity='first', start=True):
    version, policy = store.policy()
    policy.update(topic='收纳', goal='基于真实资料运营')
    policy['modules'] = {key: key != 'follow' for key in policy['modules']}
    return {'version': version, 'policy': policy, 'request_id': identity, 'start': start}


def test_setup_gaps_do_not_block_save_and_quick_run_survives_retry(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store(tmp_path / 'plan.db')
    request = body(store)
    preview = blueprints.preview(store, request)
    assert not preview['blocking']
    assert preview['readiness']['research']['ready']
    assert not preview['readiness']['publish']['ready']
    quick_start.apply(store, request)
    quick_start.apply(Store(store.path), request)
    assert store.policy()[0] == 1
    from cron.jobs import list_jobs
    assert len(list_jobs()) == 1
    calls = []
    def execute(store, policy, day, version, stage, identity, **kwargs):
        calls.append(stage)
        assert store.run_options == {'read_limit': 20, 'query_limit': 3}
        store.finish_run(identity, 'completed', stage)
    monkeypatch.setattr(runtime, '_execute', execute)
    now = datetime.now(UTC)
    runtime.tick(store, now)
    runtime.tick(Store(store.path), now)
    assert calls == ['research', 'organize', 'analytics', 'industry', 'topics', 'content', 'report']
    assert quick_start.status(store)['run']['state'] == 'partial'
    assert store.policy()[1]['limits']['source'] == 10000
    assert all(step['state'] == 'skipped' for step in quick_start.status(store)['steps'] if step['stage'] in {'publish', 'comments', 'dm'})


@pytest.mark.parametrize('quota,expected', [(10000, 20), (7, 7)])
def test_quick_collection_bounds_attempts_and_queries(tmp_path, monkeypatch, quota, expected):
    from tools import web_tools
    store = Store(tmp_path / 'sources.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='收纳', goal='整理')
    policy['modules']['research'] = True
    policy['limits']['source'] = quota
    store.configure(policy, 0)
    calls, reads = [], []
    def search(query, limit):
        calls.append(query)
        return json.dumps({'data': {'web': [{'url': f'https://example.org/{i}'} for i in range(40)]}})
    async def extract(urls, **kwargs):
        reads.extend(urls)
        return json.dumps({'results': [{'content': '真实的来源正文 ' + urls[0]}]})
    monkeypatch.setattr(web_tools, 'web_search_tool', search)
    monkeypatch.setattr(web_tools, 'web_extract_tool', extract)
    store.run_options = {'read_limit': 20, 'query_limit': 3}
    stats = collection.collect(store, policy, '2026-11-02')
    assert len(reads) == expected and len(calls) == 3
    assert stats['attempted'] == expected and store.policy()[1]['limits']['source'] == quota
    store.run_options = None
    collection.collect(store, policy, '2026-11-02')
    assert len(reads) == (40 if quota > 20 else quota)


def test_takeover_does_not_pause_non_browser_work_and_release_keeps_global_pause(tmp_path):
    store = Store(tmp_path / 'hold.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='收纳', goal='整理')
    policy['modules']['research'] = True
    store.configure(policy, 0)
    readiness.takeover(store, 'desktop', True)
    assert not store.policy()[1]['paused']
    from plugins.operations.outcomes import StageSkipped
    with pytest.raises(StageSkipped, match='人工接管'):
        store.enqueue('account', {})
    assert store.claim('other-window') is None
    with store.connection() as db:
        assert readiness.web_held(db)
    readiness.takeover(Store(store.path), 'new-window', False)
    command = store.enqueue('account', {})
    assert store.claim('new-window')['id'] == command
    policy['paused'] = True
    store.configure(policy, 1)
    readiness.takeover(store, 'new-window', False)
    assert store.policy()[1]['paused']


def test_new_plan_boundary_and_restored_setup_skip_old_slots(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store(tmp_path / 'new.db')
    request = body(store, start=False)
    quick_start.apply(store, request)
    boundary = datetime.fromisoformat(load(store, 'plan-activation')['after'])
    assert occurrences.latest_due(store, store.policy()[1], boundary) == {}
    legacy = Store(tmp_path / 'old.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='旧主题', goal='旧目标')
    policy['modules']['dm'] = True
    legacy.configure(policy, 0)
    readiness.refresh(legacy, boundary)
    policy['knowledge'] = ['营业时间为九点至十八点']
    legacy.configure(policy, 1)
    # Login is observed, never inferred from a configured account identifier.
    from plugins.operations.login_status import observe
    legacy.claim('desktop')
    observe(legacy, {'worker': 'desktop', 'platform': 'xiaohongshu', 'state': 'logged_in', 'account_id': 'test'})
    restored = boundary + timedelta(days=1)
    readiness.refresh(legacy, restored)
    assert occurrences.latest_due(legacy, legacy.policy()[1], restored) == {}
    assert occurrences.visible_occurrences(legacy, legacy.policy()[1], restored)
    assert not readiness.conditions(Store(tmp_path / 'other.db'), policy)['dm']['ready']


def test_stale_or_empty_plan_refused_but_saved_details_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store(tmp_path / 'plan.db')
    request = body(store, start=False)
    request['policy'].update(knowledge=['已确认事实'], business_theme='custom', business_subtype='自定义经营', style='自定风格')
    request['policy']['limits']['source'] = 5
    quick_start.apply(store, request)
    assert not store.policy()[1]['enabled']
    assert store.policy()[1]['knowledge'] == ['已确认事实']
    assert store.policy()[1]['limits']['source'] == 5
    stale = {**request, 'request_id': 'stale'}
    with pytest.raises(ValueError, match='配置已变更'):
        quick_start.apply(store, stale)
    fresh = body(store, 'empty', False)
    fresh['policy']['topic'] = ''
    with pytest.raises(ValueError, match='主题'):
        quick_start.apply(store, fresh)


def test_quick_start_complete_pipeline_reuses_analysis_and_records_receipts(tmp_path, monkeypatch):
    from agent import auxiliary_client
    from tools import web_tools
    from tests.plugins.test_operations_workflow import fake_model
    from plugins.operations.login_status import observe
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setattr(auxiliary_client, 'call_llm', fake_model)
    monkeypatch.setattr(web_tools, 'web_search_tool', lambda *a, **k: '{"data":{"web":[]}}')
    async def extract(urls, **kwargs):
        return json.dumps({'results': [{'content': '路线开放时间为九点。', 'title': '公开路线信息'}]})
    monkeypatch.setattr(web_tools, 'web_extract_tool', extract)
    store = Store(tmp_path / 'complete.db')
    request = body(store)
    request['policy'].update(sources=['https://example.org/walk'], knowledge=['开放时间为九点。'])
    store.put('asset', {'authorized': True, 'name': '测试图片.png'}, 'image')
    quick_start.apply(store, request)
    store.claim('mock-desktop', busy=True)
    observe(store, {'worker': 'mock-desktop', 'platform': 'xiaohongshu', 'state': 'logged_in', 'account_id': 'me'})
    original = store.command
    submissions = []
    def consume(identity):
        command = store.claim('mock-desktop')
        assert command and command['id'] == identity
        payload = command['payload']
        if command['kind'] == 'account':
            result = {'account_id': 'me'}
        elif command['kind'] == 'inbox':
            result = {'items': [{'id': payload['kind'] + ':1', 'text': '开放时间？', 'inbound': True}]}
        else:
            submissions.append(payload['kind'])
            result = {'state': 'confirmed', 'evidence': '模拟网页回执', 'url': 'https://example.org/posted'}
        store.acknowledge(identity, 'mock-desktop', result)
        return original(identity)
    monkeypatch.setattr(store, 'command', consume)
    now = datetime.now(UTC)
    runtime.tick(store, now)
    status = quick_start.status(store)
    assert status['run']['state'] == 'completed', status
    assert set(submissions) == {'publish', 'comment', 'reply', 'dm'}
    assert store.objects('content')[0]['analysis_context']['industry_id']
    assert '模拟网页回执' in store.objects('report')[0]['markdown']
    assert status['events'] and not status['errors']
    runtime.tick(Store(store.path), now)
    assert len(submissions) == 4


def test_cancelling_first_run_keeps_records_and_prevents_later_modules(tmp_path, monkeypatch):
    from plugins.operations.plan_controls import cancel_first
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store(tmp_path / 'cancel.db')
    quick_start.apply(store, body(store))
    calls = []
    def research(store, policy, day, version):
        calls.append('research')
        cancel_first(store, store.manual_run_id)
        return {'failed': 0, 'search_errors': 0, 'not_attempted': 0, 'detail': '取消前保存的资料'}
    monkeypatch.setattr(workflow, 'research', research)
    runtime.tick(store)
    state = quick_start.status(store)
    assert state['run']['state'] == 'cancelled'
    assert len(calls) == 1
    assert any(s['state'] == 'cancelled' for s in state['steps'])
    assert not store.objects('report')


def test_interrupted_first_round_does_not_replay_claimed_stage(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store(tmp_path / 'restart.db')
    quick_start.apply(store, body(store))
    seen = []
    def crash(store, policy, day, version, stage, identity, **kwargs):
        seen.append(stage)
        raise SystemExit('simulate process termination')
    monkeypatch.setattr(runtime, '_execute', crash)
    with pytest.raises(SystemExit):
        runtime.tick(store)
    assert quick_start.status(store)['run']['state'] == 'running'
    def finish(store, policy, day, version, stage, identity, **kwargs):
        seen.append(stage)
        store.finish_run(identity, 'completed', stage)
    monkeypatch.setattr(runtime, '_execute', finish)
    runtime.tick(Store(store.path))
    assert seen.count('research') == 1
    assert seen[-1] == 'report'
    status = quick_start.status(store)
    assert status['steps'][0]['state'] == 'interrupted'
    assert status['run']['state'] == 'failed'
    assert any(error.get('stage') == 'research' for error in status['errors'])
    from plugins.operations.collection_ledger import save
    save(store, 'activation', 'plan-activation', {'after': '2026-11-02T10:00:00+00:00'})
    save(store, 'readiness', 'readiness:publish', {'after': '2026-11-02T17:00:00+08:00'})
    assert readiness.boundaries(store)['publish'] == '2026-11-02T10:00:00+00:00'
