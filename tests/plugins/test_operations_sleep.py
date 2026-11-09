"""Sleep interruption and wake probes never authorize a write or lose batch identity."""
import json
import time

from tests.plugins.test_operations_execution_pause import configured
from plugins.operations.execution_pause import pause, block, load, guard, ExecutionPaused
from plugins.operations.execution_resume import paused_runs
from plugins.operations.policy import local_day


def test_pause_catalog_uses_batch_id_and_explains_inherited_sleep(tmp_path, monkeypatch):
    import pytest
    store = configured(tmp_path, monkeypatch)
    first = store.start_run(local_day(store.policy()[1]), 'comments', '11:00', 1)
    pause(store, {'error_code': 'SYSTEM_SUSPENDED', 'error': '电脑进入睡眠，账号检查中断，尚未提交',
                  'state': 'blocked', 'dispatch_state': 'read_only', 'submitted': False})
    second = store.start_run(local_day(store.policy()[1]), 'publish', '12:00', 1)
    with pytest.raises(ExecutionPaused):
        guard(store, web=True)
    rows = {r['id']: r for r in paused_runs(store)}
    assert first in rows and second in rows
    assert rows[second]['cause_run_id'] == first
    assert '本次' in rows[second]['error'] and '未执行' in rows[second]['error']


def test_wake_probe_deduplicates_and_keeps_pause_after_login(tmp_path, monkeypatch):
    from plugins.operations.wake_revalidation import revalidate
    store = configured(tmp_path, monkeypatch)
    run = store.start_run(local_day(store.policy()[1]), 'comments', '11:00', 1)
    pause(store, {'error_code': 'SYSTEM_SUSPENDED', 'error': '电脑睡眠', 'submitted': False, 'state': 'blocked', 'dispatch_state': 'read_only'})
    account = store.scope['account']
    body = {'account_id': account, 'worker': 'worker', 'wake_epoch': 'boot-1', 'request_id': 'request-1'}
    one = revalidate(store.workspace, body)
    two = revalidate(store.workspace, {**body, 'request_id': 'request-2'})
    assert one['command_id'] == two['command_id']
    command = store.claim('worker')
    assert command['kind'] == 'account' and 175 < command['expires'] - time.time() <= 180
    store.acknowledge(command['id'], 'worker', {'state': 'logged_in', 'account_id': 'account'})
    assert revalidate(store.workspace, body)['state'] == 'ready'
    assert block(store) and load(store, run)['state'] == 'paused'
    assert not store.snapshot()['actions']


def test_late_sleep_receipt_preserves_manual_conclusion_and_origin(tmp_path, monkeypatch):
    store = configured(tmp_path, monkeypatch)
    run = store.start_run(local_day(store.policy()[1]), 'comments', '11:00', 1)
    command_id = store.enqueue('account', {})
    store.claim('worker')
    with store.connection() as db:
        db.execute('UPDATE commands SET expires=? WHERE id=?', (time.time() - 1, command_id))
    store.command(command_id)
    store.acknowledge(command_id, 'worker', {'state': 'blocked', 'submitted': False, 'dispatch_state': 'read_only',
        'error_code': 'SYSTEM_SUSPENDED', 'error': '电脑睡眠', 'sleep_started_at': time.time() - 700})
    assert block(store)['cause_command_id'] == command_id
    assert load(store, run)['error_code'] == 'SYSTEM_SUSPENDED'


def test_wake_http_is_account_scoped_and_does_not_enqueue_during_takeover(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from plugins.operations.dashboard.workspace_api import router
    from plugins.operations.readiness import takeover
    store = configured(tmp_path, monkeypatch)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    body = {'account_id': store.scope['account'], 'worker': 'worker', 'wake_epoch': 'wake-http', 'request_id': 'request-http'}
    takeover(store, 'worker', True)
    assert client.post('/workspaces/worker/revalidate', json=body).json()['state'] == 'deferred'
    with store.connection() as db:
        assert db.execute('SELECT count(*) FROM commands').fetchone()[0] == 0
    takeover(store, 'worker', False)
    assert client.post('/workspaces/worker/revalidate', json=body).json()['state'] == 'checking'
    assert client.post('/workspaces/worker/revalidate', json={**body, 'account_id': 'other-profile'}).status_code == 400


def test_sleep_fact_after_success_does_not_reopen_or_replace_a_result(tmp_path, monkeypatch):
    from plugins.operations.sleep_receipts import accept
    store = configured(tmp_path, monkeypatch)
    command = store.enqueue('account', {})
    store.claim('worker')
    store.acknowledge(command, 'worker', {'state': 'logged_in', 'account_id': 'account'})
    body = {'id': command, 'worker': 'worker', 'result': {'error_code': 'SYSTEM_SUSPENDED', 'error': '睡眠',
            'power_epoch': 'wake', 'dispatch_state': 'read_only', 'submitted': False}}
    assert accept(store, body) == accept(store, body) == {'ok': True}
    assert store.command(command)['result']['state'] == 'logged_in'
    assert block(store) is None
    assert len(store.objects('power_interruption')) == 1


def test_unknown_submission_sleep_receipt_cannot_overwrite_manual_success(tmp_path, monkeypatch):
    from plugins.operations.sleep_receipts import accept
    from plugins.operations.service import resolve_action
    store = configured(tmp_path, monkeypatch)
    run = store.start_run(local_day(store.policy()[1]), 'publish', 'sleep-submit', 1)
    command = store.enqueue('account', {})
    store.claim('worker')
    with store.connection() as db:
        db.execute("INSERT INTO actions VALUES ('action','2026-11-07',1,'publish','target','executing','{}','{}','2026-11-07T00:00:00+00:00')")
        db.execute("UPDATE commands SET kind='publish',action_id='action',expires=? WHERE id=?", (time.time() - 1, command))
    assert store.command(command)['state'] == 'unknown'
    resolve_action(store, 'action', 'published', '已在实际页面核实发布成功')
    assert accept(store, {'id': command, 'worker': 'worker', 'result': {'error_code': 'SYSTEM_SUSPENDED',
        'error': '电脑睡眠，提交结果未知', 'power_epoch': 'wake', 'dispatch_state': 'submission_started', 'submitted': True}})['ok']
    with store.connection() as db:
        row = db.execute("SELECT state,result FROM actions WHERE id='action'").fetchone()
    assert row['state'] == 'published' and json.loads(row['result'])['manual_verification']['evidence']
    assert load(store, run)['state'] == 'paused'


def test_old_scheduled_pause_without_own_record_projects_history_without_rewriting(tmp_path, monkeypatch):
    from plugins.operations.pause_origin import project_runs
    store = configured(tmp_path, monkeypatch)
    source = store.start_run(local_day(store.policy()[1]), 'comments', 'old', 1)
    pause(store, {'error_code': 'SYSTEM_SUSPENDED', 'error': '电脑睡眠', 'submitted': False, 'dispatch_state': 'read_only'})
    target = store.start_run(local_day(store.policy()[1]), 'publish', 'new', 1)
    store.finish_run(target, 'paused', '电脑睡眠')
    with store.connection() as db:
        row = dict(db.execute('SELECT * FROM runs WHERE id=?', (target,)).fetchone())
    projected = project_runs(store, [row])[0]
    assert projected['pause']['cause_run_id'] == source
    assert '本次尚未执行' in projected['detail']
    assert row['detail'] == '电脑睡眠' and load(store, target) is None


def test_old_sleep_fact_cannot_reblock_an_account_after_explicit_clearance(tmp_path, monkeypatch):
    from plugins.operations.sleep_receipts import accept
    from plugins.operations.execution_pause import clear_block
    store = configured(tmp_path, monkeypatch)
    store.start_run(local_day(store.policy()[1]), 'comments', 'old-command', 1)
    command = store.enqueue('account', {})
    store.claim('worker')
    with store.connection() as db:
        db.execute('UPDATE commands SET expires=? WHERE id=?', (time.time() - 1, command))
    store.command(command)
    with store.connection() as db:
        clear_block(store, db)
    accept(store, {'id': command, 'worker': 'worker', 'result': {'error_code': 'SYSTEM_SUSPENDED', 'error': '旧睡眠回执',
        'power_epoch': 'old-wake', 'dispatch_state': 'read_only', 'submitted': False}})
    assert block(store) is None
    assert len(store.objects('power_interruption')) == 1


def test_current_resumed_batch_still_pauses_if_it_sleeps_again(tmp_path, monkeypatch):
    from plugins.operations.sleep_receipts import accept
    from plugins.operations.store import encoded
    store = configured(tmp_path, monkeypatch)
    run = store.start_run(local_day(store.policy()[1]), 'comments', 'resume-sleep', 1)
    old = pause(store, {'error_code': 'SYSTEM_SUSPENDED', 'error': '第一次睡眠'})
    with store.connection() as db:
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded({**old, 'state': 'running'}), 'execution-pause:' + run))
    command = store.enqueue('account', {})
    store.claim('worker')
    accept(store, {'id': command, 'worker': 'worker', 'result': {'error_code': 'SYSTEM_SUSPENDED', 'error': '第二次睡眠',
        'power_epoch': 'new-wake', 'dispatch_state': 'read_only', 'submitted': False}})
    assert load(store, run)['state'] == 'paused'
    assert block(store)['error'] == '第二次睡眠'
