"""Batch cancellation fences new work and preserves in-flight submission uncertainty."""
import json
import time
from types import SimpleNamespace

import pytest

from devtools import operations_debug as debug
from devtools.operations_debug_cancel import cancel_all
from plugins.operations.batch_cancellation import BatchCancelled, worker_commands
from plugins.operations.policy import local_day
from plugins.operations.store import Store
from tests.plugins.test_operations import enable


def active(tmp_path, monkeypatch, batch='debug:one'):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('development:\n  operations_debug: true\n')
    store = debug.DebugStore(batch)
    version, policy = enable(store)
    store.manual_run_id = batch
    data = debug.new_record(batch, 'publish', '图文发布', version, local_day(policy))
    store.put('debug_run', data, batch)
    return store, data, policy


def test_cancel_is_idempotent_keeps_finished_work_and_survives_restart(tmp_path, monkeypatch):
    store, data, _ = active(tmp_path, monkeypatch)
    data.update(steps=[{'id': 'topics', 'state': 'completed'}, {'id': 'publish', 'state': 'running'}, {'id': 'report', 'state': 'pending'}])
    debug.update_record(store, data)
    store.put('content', {'title': '保留草稿'}, 'draft')
    action = store.reserve_action({'kind': 'publish', 'account_id': 'me', 'target': 'draft', 'content': {}}, data['version'])
    other = Store(tmp_path / 'other.db')
    other.put('debug_run', {**data, 'id': 'debug:other'}, 'debug:other')
    result = cancel_all(store, 'cancel-one')
    assert result['cancelled'] == 1 and result['queued_commands_cancelled'] == 1
    store.put('debug_run', {**data, 'id': 'debug:later'}, 'debug:later')
    assert cancel_all(store, 'cancel-one') == result
    with store.connection() as db:
        assert json.loads(db.execute('SELECT data FROM objects WHERE id=?', ('debug:later',)).fetchone()[0])['state'] == 'running'
    assert debug.record(store, data['id'])['steps'][0]['state'] == 'completed'
    assert store.snapshot()['actions'][0]['state'] == 'cancelled'
    assert store.objects('content')[0]['id'] == 'draft'
    assert other.objects('debug_run')[0]['state'] == 'running'
    restarted = debug.DebugStore(data['id'])
    with pytest.raises(BatchCancelled):
        restarted.renew()
    data.update(state='completed')
    debug.update_record(store, data)
    assert data['state'] == 'cancelled'
    assert store.snapshot()['actions'][0]['id'] == action


def test_running_web_command_is_signalled_and_pre_submit_steps_are_rejected(tmp_path, monkeypatch):
    from plugins.operations.browser_evidence import record_step
    store, data, _ = active(tmp_path, monkeypatch)
    store.reserve_action({'kind': 'publish', 'account_id': 'me', 'target': 'draft', 'content': {}}, data['version'])
    command = store.claim('desktop')
    cancel_all(store, 'stop')
    with store.connection() as db:
        assert worker_commands(db, 'desktop') == [command['id']]
        assert worker_commands(db, 'other-worker') == []
    with pytest.raises(BatchCancelled):
        record_step(store, command['id'], 'desktop', {'sequence': 1, 'name': 'submit', 'phase': 'started'})
    store.acknowledge(command['id'], 'desktop', {'state': 'blocked', 'error_code': 'BATCH_CANCELLED',
        'submitted': False, 'dispatch_state': 'read_only'})
    assert store.snapshot()['actions'][0]['state'] == 'cancelled'
    from plugins.operations.execution_pause import block
    assert block(store) is None
    with store.connection() as db:
        assert not worker_commands(db, 'desktop')


def test_submitted_action_retains_read_only_verification_after_batch_cancel(tmp_path, monkeypatch):
    from plugins.operations.browser_evidence import record_step
    store, data, _ = active(tmp_path, monkeypatch)
    store.reserve_action({'kind': 'publish', 'account_id': 'me', 'target': 'draft', 'content': {}}, data['version'])
    command = store.claim('desktop')
    cancel_all(store, 'stop')
    store.acknowledge(command['id'], 'desktop', {'state': 'unknown', 'error_code': 'BATCH_CANCELLED',
        'submitted': True, 'dispatch_state': 'submission_started'})
    assert store.snapshot()['actions'][0]['state'] == 'unknown'
    check = store.claim('desktop')
    assert check['kind'] == 'verify'
    record_step(store, check['id'], 'desktop', {'sequence': 1, 'name': 'verify_publication', 'phase': 'started'})
    store.acknowledge(check['id'], 'desktop', {'state': 'published', 'evidence': '实际页面核对成功',
        'publication': {'execution': 'verified', 'platform': 'published', 'content': 'matched'}})
    assert store.snapshot()['actions'][0]['state'] == 'published'
    assert debug.record(store, data['id'])['state'] == 'cancelled'


def test_pipeline_cancellation_stops_following_stages_and_keeps_terminal_state(tmp_path, monkeypatch):
    from plugins.operations import workflow
    store, _, _policy = active(tmp_path, monkeypatch)
    calls = []
    def collect(current, *_args):
        calls.append('research')
        cancel_all(current, 'stop-pipeline')
        return {'detail': '已读取的资料保留', 'usable': 1}
    monkeypatch.setattr(workflow, 'research', collect)
    monkeypatch.setattr(workflow, 'topics', lambda *_args: calls.append('topics'))
    result = debug.execute({'task': 'pipeline', 'tasks': ['research', 'topics'], 'version': store.policy()[0], 'request_id': 'pipeline'})
    assert result['state'] == 'cancelled'
    assert calls == ['research']
    assert all(step['state'] == 'cancelled' for step in result['steps'])


def test_cancel_during_model_call_keeps_receipt_and_stops_processing(tmp_path, monkeypatch):
    from plugins.operations.model import generate
    from agent import auxiliary_client
    store, data, policy = active(tmp_path, monkeypatch)
    def response(**_kwargs):
        cancel_all(store, 'stop-model')
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))])
    monkeypatch.setattr(auxiliary_client, 'call_llm', response)
    with pytest.raises(BatchCancelled):
        generate(store, policy, data['day'], '输出结构化内容', {})
    traces = store.objects('model_trace')
    assert traces[0]['raw_response'] == '{}'
    assert traces[0]['state'] == 'cancelled'
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM events WHERE kind='usage'").fetchone()[0] == 1


def test_cancelled_command_expiry_does_not_pause_other_batches_and_keeps_uncertainty(tmp_path, monkeypatch):
    from plugins.operations.execution_pause import block
    store, data, _ = active(tmp_path, monkeypatch)
    store.reserve_action({'kind': 'publish', 'account_id': 'me', 'target': 'draft', 'content': {}}, data['version'])
    command = store.claim('desktop')
    cancel_all(store, 'stop')
    with store.connection() as db:
        db.execute('UPDATE commands SET expires=? WHERE id=?', (time.time() - 1, command['id']))
    assert store.command(command['id'])['state'] == 'unknown'
    assert block(store) is None
    store.acknowledge(command['id'], 'desktop', {'state': 'blocked', 'error_code': 'BATCH_CANCELLED',
        'submitted': False, 'dispatch_state': 'read_only'})
    assert store.snapshot()['actions'][0]['state'] == 'cancelled'


def test_paused_batch_cannot_resume_after_cancel_and_cancel_api_is_private(tmp_path, monkeypatch):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from devtools.operations_resume import resume
    store, data, _ = active(tmp_path, monkeypatch)
    data['state'] = 'paused'
    debug.update_record(store, data)
    store.put('execution_pause', {'state': 'paused'}, 'execution-pause:' + data['id'])
    app = FastAPI()
    app.include_router(debug.router)
    client = TestClient(app)
    assert client.post('/debug/cancel-all', json={'request_id': 'stop'}).json()['cancelled'] == 1
    with pytest.raises(HTTPException) as failure:
        resume(data['id'], {'request_id': 'resume', 'expected_revision': 1})
    assert failure.value.status_code == 409
    assert store.objects('execution_pause')[0]['state'] == 'cancelled'
    (tmp_path / 'config.yaml').write_text('development:\n  operations_debug: false\n')
    assert client.post('/debug/cancel-all', json={'request_id': 'stop-again'}).status_code == 404


def test_cancelled_owner_holds_lease_until_it_exits_and_stale_process_identity_is_recovered(tmp_path, monkeypatch):
    store, data, _ = active(tmp_path, monkeypatch)
    assert store.lease(data['id'])
    cancel_all(store, 'stop')
    next_store = Store()
    assert not next_store.lease('debug:new')
    # A PID reused by a later process is not the original execution owner.
    with store.connection() as db:
        db.execute("UPDATE objects SET data=json_set(data,'$.process_started',?) WHERE id=?", (data['process_started'] - 1, data['id']))
    assert next_store.lease('debug:new')
