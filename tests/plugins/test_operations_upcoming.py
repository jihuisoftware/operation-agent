"""Pending step cancellation is durable and shares execution's SQLite claim boundary."""
from datetime import datetime, UTC, timedelta
import pytest

from plugins.operations.store import Store
from plugins.operations.upcoming import upcoming, cancel
from plugins.operations.runtime import tick, ensure_schedule

NOW = datetime(2026, 10, 31, 0, 30, tzinfo=UTC)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    _, policy = store.policy()
    policy.update(enabled=True, topic='个人成长', goal='整理来源')
    policy['modules'] = {m: m in {'research', 'report'} for m in policy['modules']}
    store.configure(policy, 0)
    return store


def test_cancel_one_slot_persists_and_leaves_tomorrow_and_other_modules(store, monkeypatch):
    from plugins.operations import workflow
    calls = []
    monkeypatch.setattr(workflow, 'research', lambda *args: calls.append('research'))
    view = upcoming(store, NOW)
    step = next(s for s in view['steps'] if s['stage'] == 'research')
    cancel(store, {**step, 'version': view['version']}, NOW)
    cancel(Store(), {**step, 'version': view['version']}, NOW)
    tick(Store(), NOW + timedelta(minutes=30))
    assert calls == []
    persisted = upcoming(Store(), NOW)
    assert next(s for s in persisted['steps'] if s['stage'] == 'research' and s['day'] == step['day'])['state'] == 'cancelled'
    tick(Store(), NOW + timedelta(days=1, minutes=30))
    assert calls == ['research']
    assert any(s['stage'] == 'report' and s['state'] == 'pending' for s in persisted['steps'])


def test_cancelled_report_is_not_regenerated_as_offline_catchup(store, monkeypatch):
    from plugins.operations import workflow
    monkeypatch.setattr(workflow, 'research', lambda *args: None)
    view = upcoming(store, NOW)
    report = next(s for s in view['steps'] if s['stage'] == 'report')
    cancel(store, {**report, 'version': view['version']}, NOW)
    with store.connection() as db:
        db.execute("UPDATE events SET at=? WHERE kind='policy'", (NOW.isoformat(),))
    tick(Store(), datetime(2026, 11, 1, 0, tzinfo=UTC))
    assert not Store().objects('report', report['day'])


def test_execution_and_cancellation_have_exactly_one_winner(store):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    view = upcoming(store, NOW)
    step = view['steps'][0]
    barrier = Barrier(2)
    def execute():
        worker = Store()
        barrier.wait(timeout=10)
        return worker.start_run(step['day'], step['stage'], step['slot'], view['version'])
    def cancel_now():
        worker = Store()
        barrier.wait(timeout=10)
        try:
            cancel(worker, {**step, 'version': view['version']}, NOW)
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        execution, cancellation = pool.submit(execute), pool.submit(cancel_now)
        started, cancelled = execution.result(timeout=15), cancellation.result(timeout=15)
    assert bool(started) != cancelled
    with store.connection() as db:
        rows = db.execute('SELECT state FROM runs WHERE day=? AND stage=? AND slot=?',
                          (step['day'], step['stage'], step['slot'])).fetchall()
    assert [row[0] for row in rows] == ['cancelled' if cancelled else 'running']


def test_manual_pending_step_cancellation_is_scoped_to_batch_and_rejects_started(store):
    from cron import executions, task_history, jobs
    from plugins.operations.progress import planned_steps
    from plugins.operations.manual import summary
    job_id = ensure_schedule(store)
    execution = executions.create_execution(job_id, source='manual-test')
    executions.mark_execution_running(execution['id'])
    version, policy = store.policy()
    task_history.declare(execution['id'], planned_steps(store, policy, NOW, execution['id']), {'day': '2026-10-31', 'manual': True})
    view = upcoming(store, NOW)
    pending = next(s for s in view['manual'] if s['stage'] == 'research')
    cancel(store, {**pending, 'version': version}, NOW)
    assert store.start_run(pending['day'], pending['stage'], pending['slot'], version) is None
    assert task_history.detail(jobs.get_job(job_id))['steps'][0]['state'] == 'cancelled'
    assert '取消 1' in summary(store, pending['day'], pending['slot'])
    assert store.start_run(pending['day'], pending['stage'], 'manual:new-batch', version)
    report = next(s for s in view['manual'] if s['stage'] == 'report')
    store.start_run(report['day'], report['stage'], report['slot'], version)
    with pytest.raises(ValueError, match='已经开始'):
        cancel(store, {**report, 'version': version}, NOW)
    with pytest.raises(ValueError, match='规则已变化'):
        cancel(store, {**pending, 'version': version - 1}, NOW)
    executions.finish_execution(execution['id'], success=True)
