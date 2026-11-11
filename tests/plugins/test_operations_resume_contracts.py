"""Continuation crosses real private HTTP, queue evidence and account ownership boundaries."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from plugins.operations import execution_pause, execution_resume, model, workflow
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.workspaces import Workspaces
from tests.waiting import wait_until


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('{}')
    directory = Workspaces()
    store = directory.store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='恢复契约', goal='继续未完成工作', account_id='me')
    policy['modules'].update(comments=True, report=True, analytics=True)
    policy['allowed'].update(comment=True, reply=False)
    store.configure(policy, 0)
    return directory, store, policy


def paused_run(store, policy, stage='report'):
    identity = store.start_run(local_day(policy), stage, '09:00', 1)
    saved = execution_pause.pause(store, {'error_code': 'AUTH_REQUIRED', 'error': '账号已退出', 'submitted': False})
    store.finish_run(identity, 'paused', '账号已退出')
    return saved


def test_resume_probe_steps_work_under_block_and_double_continue_is_idempotent(configured):
    from hermes_cli import web_server
    _, store, policy = configured
    saved = paused_run(store, policy)
    params = {'business_id': store.scope['business_id'], 'topic_id': store.scope['id']}
    base = '/api/plugins/operations'
    path = base + '/runs/' + saved['id'] + '/resume'
    body = {'request_id': 'continue-once', 'expected_revision': saved['revision']}
    with TestClient(web_server.app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        assert client.post(path, params=params, json=body).status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        future = pool.submit(client.post, path, params=params, json=body)
        try:
            def poll():
                response = client.post(base + '/worker/poll', params=params, json={'worker': 'desktop'})
                assert response.status_code == 200, response.text
                return response.json().get('command')
            command = wait_until(poll, timeout=10)
            assert command['kind'] == 'account' and command['payload']['resume_probe'] is True
            assert execution_pause.block(store)
            duplicate = client.post(path, params=params, json=body)
            assert duplicate.status_code in (200, 409), duplicate.text
            if duplicate.status_code == 200:
                assert duplicate.json()['state'] in {'checking', 'running'}
            for sequence, name, phase in ((1, 'execution', 'started'), (2, 'account', 'started'),
                                          (2, 'account', 'completed'), (1, 'execution', 'completed')):
                response = client.post(base + '/worker/steps', params=params, json={
                    'command_id': command['id'], 'worker': 'desktop', 'sequence': sequence, 'name': name, 'phase': phase,
                    **({'result': {'state': 'logged_in', 'account_id': 'me'}} if phase == 'completed' else {})})
                assert response.status_code == 200, response.text
            ack = client.post(base + '/worker/ack', params=params, json={
                'id': command['id'], 'worker': 'desktop', 'result': {'state': 'logged_in', 'account_id': 'me'}})
            assert ack.status_code == 200, ack.text
            response = future.result(timeout=10)
            assert response.status_code == 200, response.text
            assert response.json()['state'] == 'completed'
            repeated = client.post(path, params=params, json=body)
            assert repeated.status_code == 200 and repeated.json() == response.json()
            with store.connection() as db:
                assert db.execute("SELECT count(*) FROM commands WHERE json_extract(payload,'$.resume_probe')=1").fetchone()[0] == 1
            assert execution_pause.block(store) is None
        finally:
            if not future.done():
                # Release the waiting server on test failure without touching any real worker.
                with store.connection() as db:
                    db.execute("UPDATE commands SET state='cancelled' WHERE state IN ('queued','running')")
                future.result(timeout=10)


def test_account_block_reaches_sibling_web_work_but_allows_offline_model(configured, monkeypatch):
    directory, store, policy = configured
    execution_pause.pause(store, {'error_code': 'AUTH_REQUIRED', 'error': '账号已退出'})
    scope = directory.create('另一个主题', business=store.scope['business_id'])
    sibling = directory.store(scope['business_id'], scope['topic_id'])
    sibling.configure({**policy, 'topic': '另一个主题'}, 0)
    assert execution_pause.block(sibling)['error_code'] == 'AUTH_REQUIRED'
    with pytest.raises(execution_pause.ExecutionPaused):
        sibling.enqueue('inbox', {'kind': 'comment', 'account_id': 'me'})
    monkeypatch.setattr('agent.auxiliary_client.call_llm', lambda **kwargs: SimpleNamespace(
        usage={'total_tokens': 3}, choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))]))
    assert model.generate(sibling, sibling.policy()[1], local_day(policy), '离线分析', {}) == {}
    assert execution_pause.block(sibling)


@pytest.mark.parametrize('state', ['unknown', 'submitted'])
def test_uncertain_action_blocks_resume_before_login_probe(configured, monkeypatch, state):
    _, store, policy = configured
    saved = paused_run(store, policy, 'comments')
    with store.connection() as db:
        db.execute("INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?)", ('uncertain', local_day(policy), 1,
                   'comment', 'note', state, json.dumps({'account_id': 'me', 'run_id': saved['run_id']}), '{}', '2026-11-04T00:00:00+00:00'))
    monkeypatch.setattr(workflow, 'browser', lambda *args, **kwargs: pytest.fail('不得在未知动作核对前发起恢复探测'))
    with pytest.raises(ValueError, match='未知|未完成'):
        execution_resume.prepare(store, saved['id'], {'request_id': 'unsafe', 'expected_revision': saved['revision']})


def test_resume_reuses_proved_unsubmitted_action_and_existing_charge(configured, monkeypatch):
    from hermes_cli import web_server
    _, store, policy = configured
    run = store.start_run(local_day(policy), 'comments', '10:00', 1)
    action = store.reserve_action({'kind': 'comment', 'account_id': 'me', 'target': 'note:one', 'text': '有来源依据的评论'}, 1)
    original = store.claim('desktop')
    store.acknowledge(original['id'], 'desktop', {'state': 'blocked', 'submitted': False, 'dispatch_state': 'read_only',
        'error_code': 'AUTH_REQUIRED', 'error': '账号退出，尚未提交'})
    store.finish_run(run, 'paused', '账号退出，尚未提交')
    saved = execution_pause.load(store, run)
    assert saved and action
    with store.connection() as db:
        charges = db.execute("SELECT coalesce(sum(amount),0) FROM directory.charges WHERE kind='comment'").fetchone()[0]
    assert charges == 1
    monkeypatch.setattr('agent.auxiliary_client.call_llm', lambda **kwargs: pytest.fail('恢复已生成动作不应重新调用模型'))
    params = {'business_id': store.scope['business_id'], 'topic_id': store.scope['id']}
    base = '/api/plugins/operations'
    with TestClient(web_server.app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        future = pool.submit(client.post, base + '/runs/' + run + '/resume', params=params,
                             json={'request_id': 'continue-action', 'expected_revision': saved['revision']})
        try:
            def poll():
                response = client.post(base + '/worker/poll', params=params, json={'worker': 'desktop'})
                assert response.status_code == 200, response.text
                return response.json().get('command')
            probe = wait_until(poll, timeout=10)
            assert probe['kind'] == 'account' and probe['payload']['resume_probe']
            assert client.post(base + '/worker/ack', params=params, json={'id': probe['id'], 'worker': 'desktop',
                               'result': {'state': 'logged_in', 'account_id': 'me'}}).status_code == 200
            continued = wait_until(poll, timeout=10)
            assert continued['kind'] == 'interact' and continued['payload']['target'] == 'note:one'
            assert continued['id'] != original['id']
            assert client.post(base + '/worker/ack', params=params, json={'id': continued['id'], 'worker': 'desktop',
                               'result': {'state': 'confirmed', 'evidence': '页面显示评论成功'}}).status_code == 200
            response = future.result(timeout=10)
            assert response.status_code == 200, response.text
            assert response.json()['state'] == 'completed', response.text
            with store.connection() as db:
                assert db.execute("SELECT count(*) FROM actions").fetchone()[0] == 1
                assert db.execute("SELECT id,state FROM actions").fetchone()[:] == (action, 'confirmed')
                assert db.execute("SELECT coalesce(sum(amount),0) FROM directory.charges WHERE kind='comment'").fetchone()[0] == charges
                assert db.execute('SELECT action_id FROM commands WHERE id=?', (continued['id'],)).fetchone()[0] == action
        finally:
            if not future.done():
                with store.connection() as db:
                    db.execute("UPDATE commands SET state='cancelled' WHERE state IN ('queued','running')")
                future.result(timeout=10)
