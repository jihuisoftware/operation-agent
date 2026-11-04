"""Normal and quick pipelines require explicit selection while preserving legacy replay and resume."""
from copy import deepcopy
import json

import pytest
from fastapi import HTTPException

from devtools import operations_debug as debug
from plugins.operations import workflow
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store
from tests.devtools.test_operations_pipeline import model
from tests.plugins.operations_support import prepare_materials


@pytest.fixture
def selected_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('development:\n  operations_debug: true\n')
    store = Store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='步行', goal='路线资料', account_id='me', sources=['https://example.org/walk'],
                  knowledge=['开放时间为九点。'], follow_terms=['步行'])
    policy['modules'] = {kind: True for kind in policy['modules']}
    policy['allowed'] = {kind: False for kind in policy['allowed']}
    store.configure(policy, 0)
    store.put('asset', {'authorized': True, 'name': '自有图片.png'}, 'image')
    from tools import web_tools
    monkeypatch.setattr(web_tools, 'web_search_tool', lambda *args, **kwargs: json.dumps({'data': {'web': []}}))
    async def extract(*args, **kwargs):
        return json.dumps({'results': [{'content': '步行路线开放时间为九点。'}]})
    monkeypatch.setattr(web_tools, 'web_extract_tool', extract)
    from agent import auxiliary_client
    calls, submitted = [], []
    def generate(**kwargs):
        calls.append(json.loads(kwargs['messages'][1]['content']))
        return model(**kwargs)
    monkeypatch.setattr(auxiliary_client, 'call_llm', generate)
    original = Store.command
    def consume(self, identity):
        worker = Store(self.path, workspace=self.workspace, scope=self.scope)
        command = worker.claim('simulated-desktop')
        while command and command['kind'] == 'verify' and command['id'] != identity:
            worker.acknowledge(command['id'], 'simulated-desktop', {'state': 'unknown', 'evidence': '只读核对仍待审核'})
            command = worker.claim('simulated-desktop')
        assert command and command['id'] == identity
        payload = command['payload']
        if command['kind'] == 'account':
            result = {'state': 'logged_in', 'account_id': 'me'}
        elif command['kind'] == 'inbox':
            result = {'items': [{'id': payload['kind'] + ':1', 'text': '步行，开放时间？', 'inbound': True, 'follows_me': True}]}
        else:
            submitted.append(payload)
            result = {'state': 'confirmed', 'evidence': '模拟页面回执', 'url': 'https://example.org/result'}
        worker.acknowledge(identity, 'simulated-desktop', result)
        return original(self, identity)
    monkeypatch.setattr(debug.DebugStore, 'command', consume)
    store.claim('simulated-desktop', busy=True)
    return store, calls, submitted


def request(identity, tasks):
    return {'task': 'pipeline', 'mode': 'quick', 'version': 1, 'request_id': identity,
            'external_actions': 'execute_once', 'tasks': tasks}


def source(store):
    policy = store.policy()[1]
    return store.put('source', {'day': local_day(policy), 'scope_topic': policy['topic'], 'title': '既有来源',
                               'url': 'https://example.org/existing', 'text': '步行路线开放时间为九点。', 'state': 'read'}, 'existing-source')


def ready_draft(store):
    source(store)
    return store.put('content', {'day': local_day(store.policy()[1]), 'version': 1, 'title': '原草稿', 'body': '开放时间为九点。',
                                'ready': True, 'source_ids': ['existing-source'], 'asset_ids': ['image']}, 'original-ready-draft')


def test_research_and_report_run_in_catalog_order_without_other_models_or_grants(selected_environment):
    store, calls, submitted = selected_environment
    result = debug.execute(request('research-report', ['report', 'research']))
    assert [step['id'] for step in result['steps']] == ['research', 'report']
    assert not calls and not submitted
    assert not store.objects('debug_action_grant')
    assert store.objects('report')


def test_unselected_prerequisites_use_valid_materials_without_adding_steps(selected_environment, monkeypatch):
    store, calls, submitted = selected_environment
    source(store)
    policy = store.policy()[1]
    prepare_materials(store, policy, local_day(policy), monkeypatch)
    result = debug.execute(request('topics-only', ['topics']))
    assert [step['id'] for step in result['steps']] == ['topics']
    assert result['steps'][0]['state'] == 'completed'
    assert len(calls) == 1 and not submitted
    assert store.objects('report') and not store.objects('debug_action_grant')
    with store.connection() as db:
        assert {row[0] for row in db.execute('SELECT stage FROM runs WHERE slot=? OR substr(slot,1,?)=?',
                (result['id'], len(result['id']) + 1, result['id'] + ':'))} == {'topics'}


def test_publish_only_binds_existing_draft_and_grants_only_publish(selected_environment, monkeypatch):
    store, calls, submitted = selected_environment
    original_id = ready_draft(store)
    original = workflow.publish
    def publish(active, policy, day, version, *, content_id=None):
        store.put('content', {'day': day, 'version': version, 'title': '后来的草稿', 'body': '不能替换原版本',
                              'ready': True, 'source_ids': ['existing-source'], 'asset_ids': ['image']}, 'later-draft')
        return original(active, policy, day, version, content_id=content_id)
    monkeypatch.setattr(workflow, 'publish', publish)
    result = debug.execute(request('publish-only', ['publish']))
    assert [step['id'] for step in result['steps']] == ['publish']
    assert result['steps'][0]['state'] == 'completed'
    assert len(submitted) == 1 and submitted[0]['content']['id'] == original_id
    assert [row['actions'] for row in store.objects('debug_action_grant')] == [['publish']]
    assert len(calls) == 1  # The existing draft still undergoes publication-time quality review.


def test_failed_selected_prerequisite_cannot_fall_back_to_old_ready_draft(selected_environment, monkeypatch):
    store, _, submitted = selected_environment
    ready_draft(store)
    def failed(*_):
        raise ValueError('本次选题失败')
    monkeypatch.setattr(workflow, 'topics', failed)
    result = debug.execute(request('failed-selected', ['publish', 'content', 'topics']))
    assert [step['id'] for step in result['steps']] == ['topics', 'content', 'publish']
    assert [step['state'] for step in result['steps']] == ['failed', 'skipped', 'skipped']
    assert not submitted
    assert store.objects('report')


def test_selected_external_grant_does_not_include_other_action_kinds(selected_environment):
    store, _, submitted = selected_environment
    result = debug.execute(request('one-comment', ['comment']))
    assert [step['id'] for step in result['steps']] == ['comment']
    assert [payload['kind'] for payload in submitted] == ['comment']
    assert [row['actions'] for row in store.objects('debug_action_grant')] == [['comment']]


def test_request_replay_compares_the_normalized_selection(selected_environment):
    _, calls, _ = selected_environment
    body = request('same-request', ['report', 'research'])
    first = debug.execute(body)
    assert debug.execute({**body, 'tasks': ['research', 'report']}) == first
    with pytest.raises(HTTPException) as conflict:
        debug.execute({**body, 'tasks': ['report']})
    assert conflict.value.status_code == 409
    assert not calls


@pytest.mark.parametrize('changes', [
    {'tasks': []}, {'tasks': ['research', 'research']}, {'tasks': ['unknown']}, {'tasks': 'research'}, {'tasks': None},
    {'task': 'research', 'tasks': ['research']},
])
def test_invalid_explicit_selection_is_rejected_before_execution(selected_environment, changes):
    store, calls, submitted = selected_environment
    with pytest.raises(HTTPException) as rejected:
        debug.execute({**request('bad-selection', ['research']), **changes})
    assert rejected.value.status_code == 400
    assert not store.objects('debug_run') and not calls and not submitted


@pytest.mark.parametrize('mode', ['normal', 'quick'])
def test_new_pipeline_requires_explicit_selection(selected_environment, mode):
    store, calls, submitted = selected_environment
    body = request('missing-selection', ['research'])
    body.pop('tasks')
    body.update(mode=mode, external_actions='execute_once' if mode == 'quick' else None)
    with pytest.raises(HTTPException) as rejected:
        debug.execute(body)
    assert rejected.value.status_code == 400
    assert not store.objects('debug_run') and not calls and not submitted


@pytest.mark.parametrize('mode', ['normal', 'quick'])
def test_existing_legacy_request_without_selection_replays_unchanged_history(selected_environment, mode):
    from plugins.operations.policy import now_iso
    store, calls, submitted = selected_environment
    body = request('legacy-existing', ['research'])
    body.pop('tasks')
    body.update(mode=mode, external_actions='execute_once' if mode == 'quick' else None)
    old = debug.new_record('debug:legacy-existing', 'pipeline', '旧整链路', 1, local_day(store.policy()[1]))
    old.update(mode=mode, action_mode='execute_once' if mode == 'quick' else 'standing_policy', state='completed',
               ended=now_iso(), steps=[{'id': key, 'module': module, 'title': title, 'state': 'completed', 'detail': '旧结果'}
                                      for key, (title, module) in debug.TASKS.items()])
    store.put('debug_run', old, old['id'])
    before = debug.detail(old['id'])['run']
    assert debug.execute(body) == before
    assert debug.detail(old['id'])['run'] == before
    assert not calls and not submitted


def test_resume_keeps_only_selected_steps_and_diagnostic_report_is_not_a_business_step(selected_environment, monkeypatch):
    from devtools.operations_resume import resume
    from plugins.operations.execution_pause import ExecutionPaused, pause
    store, calls, submitted = selected_environment
    original = workflow.research
    attempts = []
    def research(active, *args):
        attempts.append(True)
        if len(attempts) == 1:
            failure = {'error_code': 'BROWSER_UNAVAILABLE', 'error': '执行环境中断', 'submitted': False}
            pause(active, failure)
            raise ExecutionPaused(failure)
        return original(active, *args)
    monkeypatch.setattr(workflow, 'research', research)
    paused = debug.execute(request('selected-resume', ['research']))
    assert paused['state'] == 'paused'
    assert [step['id'] for step in paused['steps']] == ['research']
    assert store.objects('report')
    resumed = resume(paused['id'], {'request_id': 'continue', 'expected_revision': paused['revision'], 'external_actions': 'execute_once'})
    assert [step['id'] for step in resumed['steps']] == ['research']
    assert resumed['state'] in {'completed', 'needs_attention'}
    assert len(attempts) == 2 and not calls and not submitted
    assert len(store.objects('report')) == 2


def test_private_http_preserves_selection_and_authentication(selected_environment):
    from starlette.testclient import TestClient
    from hermes_cli import web_server
    store, calls, submitted = selected_environment
    scope = {'business_id': store.scope['business_id'], 'topic_id': store.scope['id']}
    body = request('http-selection', ['report', 'research'])
    with TestClient(web_server.app) as client:
        path = '/api/plugins/operations/debug/run'
        assert client.post(path, params=scope, json=body).status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        response = client.post(path, params=scope, json=body)
        assert response.status_code == 200, response.text
        assert [step['id'] for step in response.json()['steps']] == ['research', 'report']
        assert client.post(path, params=scope, json={**body, 'tasks': ['report']}).status_code == 409
    assert not calls and not submitted and not store.objects('debug_action_grant')


@pytest.mark.parametrize('authorized', [False, True])
def test_normal_selection_runs_only_requested_late_stages_under_standing_permissions(selected_environment, authorized):
    store, calls, submitted = selected_environment
    version, policy = store.policy()
    policy['allowed']['comment'] = authorized
    store.configure(policy, version)
    body = request('normal-late-only', ['report', 'comment'])
    body.update(mode='normal', external_actions=None, version=version + 1)
    result = debug.execute(body)
    assert [step['id'] for step in result['steps']] == ['comment', 'report']
    assert result['steps'][0]['state'] == ('completed' if authorized else 'skipped')
    assert [payload['kind'] for payload in submitted] == (['comment'] if authorized else [])
    assert len(calls) == (1 if authorized else 0)
    assert all('candidates' in data for data in calls)
    assert not store.objects('debug_action_grant')


@pytest.mark.parametrize('matching_lease', [False, True])
def test_dead_debug_owner_releases_only_its_own_account_lease(selected_environment, matching_lease):
    import subprocess
    import sys
    store, _, _ = selected_environment
    with subprocess.Popen([sys.executable, '-c', 'import psutil; print(psutil.Process().create_time())'],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
        output, error = process.communicate(timeout=10)
        assert process.returncode == 0, error
        dead_pid, created = process.pid, float(output.strip())
    old = debug.new_record('debug:dead-full', 'pipeline', '已退出的旧整链路', 1, local_day(store.policy()[1]))
    old.update(pid=dead_pid, process_started=created, mode='normal', action_mode='standing_policy', steps=[
        {'id': 'research', 'module': 'research', 'title': '信息采集', 'state': 'running', 'detail': '旧任务'}])
    store.put('debug_run', old, old['id'])
    token = old['id'] if matching_lease else 'another-live-owner'
    assert store.lease(token)
    recovered = debug.record(store, old['id'])
    assert recovered['state'] == 'interrupted'
    assert '没有外部提交记录' in recovered['detail']
    assert store.lease('new-selected-run') is matching_lease
    if not matching_lease:
        with store.connection() as db:
            assert db.execute("SELECT token FROM leases WHERE id='account'").fetchone()[0] == token


def test_existing_legacy_paused_pipeline_resumes_without_rewriting_selection_history(selected_environment):
    from devtools.operations_resume import resume
    from plugins.operations.execution_pause import pause
    store, calls, submitted = selected_environment
    identity = 'debug:legacy-paused'
    store.manual_run_id = identity
    run_id = store.start_run(local_day(store.policy()[1]), 'report', identity + ':report', 1)
    paused = pause(store, {'error_code': 'BROWSER_UNAVAILABLE', 'error': '旧批次执行器中断'})
    store.finish_run(run_id, 'paused', paused['error'])
    old = debug.new_record(identity, 'pipeline', '旧整链路', 1, local_day(store.policy()[1]))
    old.update(mode='normal', action_mode='standing_policy', state='paused', revision=paused['revision'], steps=[
        {'id': key, 'module': module, 'title': title, 'state': 'paused' if key == 'report' else 'completed',
         'detail': paused['error'] if key == 'report' else '历史已完成结果'}
        for key, (title, module) in debug.TASKS.items()])
    store.put('debug_run', old, identity)
    resumed = resume(identity, {'request_id': 'continue-legacy', 'expected_revision': paused['revision']})
    assert resumed['state'] == 'completed'
    assert 'selected_tasks' not in resumed
    assert [step['id'] for step in resumed['steps']] == list(debug.TASKS)
    assert all(step['detail'] == '历史已完成结果' for step in resumed['steps'] if step['id'] != 'report')
    assert not calls and not submitted
    with store.connection() as db:
        assert db.execute('SELECT state FROM runs WHERE id=?', (run_id,)).fetchone()[0] == 'paused'
