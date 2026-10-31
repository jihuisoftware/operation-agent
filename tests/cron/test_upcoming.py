"""Cancelling an occurrence fences dispatch, without disabling future/manual runs."""
import pytest


def test_cancel_survives_reload_and_blocks_agent_but_not_new_manual_run(tmp_path, monkeypatch):
    from cron import jobs, executions, upcoming, task_history
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    job = jobs.create_job(prompt='模拟任务', schedule='every 1h')
    item = upcoming.list_upcoming([job])[0]
    upcoming.cancel(job, item['instant'], item['plan'])
    assert upcoming.list_upcoming([jobs.get_job(job['id'])])[0]['state'] == 'cancelled'
    calls = []
    for instant in (item['instant'], None):
        attempt = executions.create_execution(job['id'], source='test', scheduled_instant=instant)
        executions.mark_execution_running(attempt['id'])
        def execute(*args, **kwargs):
            calls.append('started')
            return True, '实际输出', '实际输出', None
        result = upcoming.run_planned_job({**job, 'execution_id': attempt['id']}, execute)
        executions.finish_execution(attempt['id'], success=result[0])
        if instant:
            assert calls == []
            assert '人工取消' in result[1]
            assert task_history.detail(job)['steps'][0]['state'] == 'cancelled'
    assert calls == ['started']
    assert jobs.get_job(job['id'])['enabled']


def test_stale_plan_and_started_step_cannot_be_cancelled(tmp_path, monkeypatch):
    from cron import jobs, executions, upcoming
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    job = jobs.create_job(prompt='模拟任务', schedule='every 1h')
    item = upcoming.list_upcoming([job])[0]
    changed = jobs.update_job(job['id'], {'prompt': '修改任务'})
    with pytest.raises(ValueError, match='变更'):
        upcoming.cancel(changed, item['instant'], item['plan'])
    item = upcoming.list_upcoming([changed])[0]
    attempt = executions.create_execution(job['id'], source='test', scheduled_instant=item['instant'])
    executions.mark_execution_running(attempt['id'])
    def execute(*args, **kwargs):
        with pytest.raises(ValueError, match='已经开始'):
            upcoming.cancel(changed, item['instant'], item['plan'])
        return True, '完成', '完成', None
    upcoming.run_planned_job({**changed, 'execution_id': attempt['id']}, execute)
    executions.finish_execution(attempt['id'], success=True)
