"""A live manual run must not become a failed periodic attempt or disappear from views."""
from datetime import timedelta

from hermes_time import now


def test_due_scan_defers_live_fire_without_advancing_or_creating_attempt(tmp_path, monkeypatch):
    from cron import executions, jobs
    from cron.scheduler_provider import InProcessCronScheduler

    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    job = jobs.create_job(prompt='local test', schedule='every 1m')
    claim = InProcessCronScheduler().claim_fire(job['id'], manual=True)
    executions.mark_execution_running(claim['execution_id'])
    # The run takes longer than one period; another ticker has no local registration.
    rows = jobs.load_jobs()
    slot = (now() - timedelta(seconds=20)).isoformat()
    rows[0]['next_run_at'] = slot
    jobs.save_jobs(rows)
    assert jobs.get_due_jobs() == []
    assert jobs.get_job(job['id'])['next_run_at'] == slot
    assert len(executions.list_executions(job_id=job['id'])) == 1
    # A dead/stale claim must still be eligible for the normal recovery path.
    rows = jobs.load_jobs()
    rows[0]['fire_claim']['at'] = (now() - timedelta(days=1)).isoformat()
    jobs.save_jobs(rows)
    assert [j['id'] for j in jobs.get_due_jobs()] == [job['id']]


def test_newer_failed_attempt_does_not_hide_live_owner_or_leak_profiles(tmp_path, monkeypatch):
    from cron import executions, jobs
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override

    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    job = jobs.create_job(prompt='local test', schedule='every 1m')
    active = executions.create_execution(job['id'], source='manual')
    executions.mark_execution_running(active['id'])
    refused = executions.create_execution(job['id'], source='builtin')
    executions.finish_execution(refused['id'], success=False, error='Fire claim lost')
    assert executions.live_inflight_execution(job['id'])['id'] == active['id']
    listed = jobs.list_jobs()[0]
    assert listed['active_execution']['id'] == active['id']
    assert listed['latest_execution']['id'] == refused['id']
    token = set_hermes_home_override(str(tmp_path / 'other'))
    try:
        assert executions.live_inflight_execution(job['id']) is None
    finally:
        reset_hermes_home_override(token)
    executions.finish_execution(active['id'], success=True)
    assert executions.live_inflight_execution(job['id']) is None
    assert jobs.list_jobs()[0]['active_execution'] is None


def test_ticker_registration_refuses_live_direct_fire(tmp_path, monkeypatch):
    from cron import executions, jobs, scheduler
    from cron.scheduler_provider import InProcessCronScheduler

    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    job = jobs.create_job(prompt='local test', schedule='every 1m')
    claim = InProcessCronScheduler().claim_fire(job['id'], manual=True)
    monkeypatch.setattr(scheduler, '_launch_external_cron_worker', lambda job: False)
    def during_run(job, **kwargs):
        assert scheduler.is_job_running(job['id'])
        registered = scheduler.try_register_running_job(job['id'])
        if registered:
            scheduler.release_running_job(job['id'])
        assert not registered
        return True
    monkeypatch.setattr(scheduler, '_run_one_job_body', during_run)
    try:
        assert scheduler.run_one_job(claim)
    finally:
        executions.finish_execution(claim['execution_id'], success=True)
    assert not scheduler.is_job_running(job['id'])
