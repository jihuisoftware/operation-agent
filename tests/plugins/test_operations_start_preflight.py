"""Explicit new debug work verifies current login without resuming historical batches."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from starlette.testclient import TestClient

from plugins.operations import execution_pause, workflow
from plugins.operations.login_status import observe
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.workspaces import Workspaces
from tests.waiting import wait_until


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('development:\n  operations_debug: true\n')
    store = Workspaces().store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='新批次登录检查', goal='只检查当前账号', account_id='me')
    policy['modules'].update(comments=True, report=True)
    policy['allowed']['comment'] = True
    store.configure(policy, 0)
    store.claim('desktop', busy=True)
    return store, policy


@pytest.mark.parametrize('code', ['AUTH_REQUIRED', 'VERIFICATION_REQUIRED'])
@pytest.mark.parametrize('entry', ['pipeline', 'single'])
def test_new_click_verifies_old_login_block_without_resuming_the_paused_batch(configured, monkeypatch, code, entry):
    from hermes_cli import web_server
    store, policy = configured
    old_run = store.start_run(local_day(policy), 'comments', '09:00', 1)
    old_pause = execution_pause.pause(store, {'error_code': code, 'error': '此前账号需要处理', 'submitted': False})
    store.finish_run(old_run, 'paused', old_pause['error'])
    observe(store, {'platform': 'xiaohongshu', 'worker': 'desktop', 'state': 'logged_in', 'account_id': 'me'})
    assert execution_pause.block(store)
    entered = []
    monkeypatch.setattr(workflow, 'interact', lambda *args, **kwargs: entered.append(True) or [])
    params = {'business_id': store.scope['business_id'], 'topic_id': store.scope['id']}
    base = '/api/plugins/operations'
    body = {'task': 'pipeline' if entry == 'pipeline' else 'comment', 'mode': 'quick', 'external_actions': 'execute_once',
            'request_id': 'new-click', 'version': 1, **({'tasks': ['comment']} if entry == 'pipeline' else {})}
    with TestClient(web_server.app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        future = pool.submit(client.post, base + '/debug/run', params=params, json=body)
        try:
            def poll():
                response = client.post(base + '/worker/poll', params=params, json={'worker': 'desktop'})
                assert response.status_code == 200, response.text
                command = response.json().get('command')
                return command or ({'finished_without_probe': future.result().json()} if future.done() else None)
            command = wait_until(poll, timeout=10)
            assert command.get('kind') == 'account', command
            assert command['payload']['resume_probe'] is True
            assert entered == []
            assert execution_pause.block(store)
            identity = {'state': 'logged_in', 'account_id': 'me'}
            for sequence, name, phase in ((1, 'execution', 'started'), (2, 'account', 'started'),
                                          (2, 'account', 'completed'), (1, 'execution', 'completed')):
                response = client.post(base + '/worker/steps', params=params, json={
                    'command_id': command['id'], 'worker': 'desktop', 'sequence': sequence, 'name': name, 'phase': phase,
                    **({'result': identity} if phase == 'completed' else {})})
                assert response.status_code == 200, response.text
            ack = client.post(base + '/worker/ack', params=params, json={'id': command['id'], 'worker': 'desktop', 'result': identity})
            assert ack.status_code == 200, ack.text
            response = future.result(timeout=10)
            assert response.status_code == 200, response.text
            assert response.json()['state'] == 'completed', response.json()
            assert entered == [True]
            assert execution_pause.block(store) is None
            preserved = execution_pause.load(store, old_run)
            assert {key: preserved[key] for key in old_pause} == old_pause
            with store.connection() as db:
                assert db.execute('SELECT state FROM runs WHERE id=?', (old_run,)).fetchone()[0] == 'paused'
                assert db.execute('SELECT kind FROM commands').fetchall()[0][0] == 'account'
                assert db.execute('SELECT count(*) FROM commands').fetchone()[0] == 1
                assert db.execute('SELECT count(*) FROM actions').fetchone()[0] == 0
            repeated = client.post(base + '/debug/run', params=params, json=body)
            assert repeated.status_code == 200 and repeated.json() == response.json()
        finally:
            if not future.done():
                with store.connection() as db:
                    db.execute("UPDATE commands SET state='cancelled' WHERE state IN ('queued','running')")
                future.result(timeout=10)


def new_attempt(store, policy, code='AUTH_REQUIRED'):
    with store.connection() as db:
        old = execution_pause.set_block(store, db, {'error_code': code, 'error': '历史阻塞'})
    store.manual_run_id = 'debug:preflight'
    store.start_run(local_day(policy), 'comments', 'debug:preflight:comment', 1)
    return old


@pytest.mark.parametrize('state', ['unknown', 'submitted', 'executing', 'queued'])
def test_new_click_can_probe_without_changing_uncertain_action_records(configured, monkeypatch, state):
    from plugins.operations.execution_preflight import verify_for_start
    import json
    store, policy = configured
    old = new_attempt(store, policy)
    with store.connection() as db:
        db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?)', ('outstanding', local_day(policy), 1,
                   'comment', 'target', state, json.dumps({'account_id': 'me'}), '{}', old['at']))
    probes = []
    monkeypatch.setattr(workflow, 'browser', lambda _store, kind, payload: probes.append((kind, payload)) or {'state': 'logged_in', 'account_id': 'me'})
    assert verify_for_start(store, 1)['state'] == 'logged_in'
    assert probes == [('account', {'resume_probe': True, 'preflight': 'explicit_start'})]
    assert execution_pause.block(store) is None
    with store.connection() as db:
        assert db.execute('SELECT state FROM actions WHERE id=?', ('outstanding',)).fetchone()[0] == state


def test_new_click_preserves_manual_takeover_and_old_auth_block(configured, monkeypatch):
    from plugins.operations.execution_preflight import verify_for_start
    from plugins.operations.readiness import takeover, web_block_reason
    store, policy = configured
    old = new_attempt(store, policy)
    takeover(store, 'desktop', True)
    monkeypatch.setattr(workflow, 'browser', lambda *args, **kwargs: pytest.fail('人工接管期间不得导航探测'))
    with pytest.raises(execution_pause.ExecutionPaused) as paused:
        verify_for_start(store, 1)
    assert paused.value.result['error_code'] == 'CONTROL_PAUSED'
    assert execution_pause.block(store) == old
    with store.connection() as db:
        assert '人工接管' in web_block_reason(db)


def test_probe_cannot_clear_a_new_negative_observation(configured, monkeypatch):
    from plugins.operations.execution_preflight import verify_for_start
    store, policy = configured
    old = new_attempt(store, policy)
    def probe(*args, **kwargs):
        observe(store, {'platform': 'xiaohongshu', 'worker': 'desktop', 'state': 'verification', 'account_id': ''})
        return {'state': 'logged_in', 'account_id': 'me'}
    monkeypatch.setattr(workflow, 'browser', probe)
    with pytest.raises(execution_pause.ExecutionPaused):
        verify_for_start(store, 1)
    current = execution_pause.block(store)
    assert current['error_code'] == 'VERIFICATION_REQUIRED' and current['revision'] > old['revision']


@pytest.mark.parametrize('change', ['policy', 'account_link', 'identity', 'day'])
def test_new_probe_revalidates_rules_and_account_ownership_before_clearing(configured, monkeypatch, change):
    from plugins.operations.execution_preflight import verify_for_start
    store, policy = configured
    old = new_attempt(store, policy)
    original_account = execution_pause.account_key(store)
    def probe(*args, **kwargs):
        if change == 'policy':
            store.configure({**policy, 'style': '已改变的规则'}, 1)
        if change == 'day':
            from datetime import date, timedelta
            tomorrow = (date.fromisoformat(local_day(policy)) + timedelta(days=1)).isoformat()
            monkeypatch.setattr('plugins.operations.execution_preflight.local_day', lambda _: tomorrow)
        if change == 'account_link':
            with store.connection() as db:
                db.execute("INSERT INTO directory.accounts(id) VALUES ('another-account')")
                db.execute("UPDATE directory.businesses SET account='another-account' WHERE id=?", (store.scope['business_id'],))
        return {'state': 'logged_in', 'account_id': 'another' if change == 'identity' else 'me'}
    monkeypatch.setattr(workflow, 'browser', probe)
    with pytest.raises(execution_pause.ExecutionPaused):
        verify_for_start(store, 1)
    with store.connection() as db:
        row = db.execute('SELECT data FROM directory.preferences WHERE id=?', ('execution-block:' + original_account,)).fetchone()
        assert row and old['error'] in row[0]


@pytest.mark.parametrize('code', ['ACCOUNT_CHANGED', 'REVALIDATION_REQUIRED'])
def test_start_preflight_does_not_clear_account_or_context_changes(configured, monkeypatch, code):
    from plugins.operations.execution_preflight import verify_for_start
    store, policy = configured
    old = new_attempt(store, policy, code)
    monkeypatch.setattr(workflow, 'browser', lambda *args, **kwargs: pytest.fail('其他中断不能作为旧登录锁自动清除'))
    assert verify_for_start(store, 1) is None
    assert execution_pause.block(store) == old


@pytest.mark.parametrize('code', ['BROWSER_UNAVAILABLE', 'COMMAND_EXPIRED'])
def test_explicit_start_rechecks_proved_read_only_interruption(configured, monkeypatch, code):
    from plugins.operations.execution_preflight import verify_for_start
    store, policy = configured
    new_attempt(store, policy, code)
    with store.connection() as db:
        execution_pause.set_block(store, db, {'error_code': code, 'error': '旧只读超时',
            'state': 'blocked', 'submitted': False, 'dispatch_state': 'read_only'})
    calls = []
    def probe(*args):
        calls.append(args[2])
        return {'state': 'logged_in', 'account_id': 'me'}
    monkeypatch.setattr(workflow, 'browser', probe)
    result = verify_for_start(store, 1)
    assert result and result['cleared_error_code'] == code
    assert calls == [{'resume_probe': True, 'preflight': 'explicit_start'}]
    assert execution_pause.block(store) is None


def test_uncertain_browser_timeout_allows_only_a_fresh_account_probe(configured, monkeypatch):
    from plugins.operations.execution_preflight import verify_for_start
    store, policy = configured
    new_attempt(store, policy, 'BROWSER_UNAVAILABLE')
    with store.connection() as db:
        execution_pause.set_block(store, db, {'error_code': 'BROWSER_UNAVAILABLE', 'error': '提交超时',
            'state': 'unknown', 'submitted': True, 'dispatch_state': 'submission_started'})
        db.execute("INSERT INTO actions VALUES ('old',?,1,'publish','draft','unknown','{}','{}',?)", (local_day(policy), '2026-11-08'))
    probes = []
    monkeypatch.setattr(workflow, 'browser', lambda _store, kind, payload: probes.append((kind, payload)) or {'state': 'logged_in', 'account_id': 'me'})
    assert verify_for_start(store, 1)['state'] == 'logged_in'
    assert probes == [('account', {'resume_probe': True, 'preflight': 'explicit_start'})]
    assert execution_pause.block(store) is None
    with store.connection() as db:
        assert db.execute("SELECT state FROM actions WHERE id='old'").fetchone()[0] == 'unknown'
