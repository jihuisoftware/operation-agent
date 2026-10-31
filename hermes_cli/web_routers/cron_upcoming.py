"""Authenticated queue operations bind their Profile before touching scheduler state."""
from fastapi import HTTPException


def read_upcoming(profile=None):
    from . import cron
    from cron.upcoming import list_upcoming
    selected = profile or 'default'
    if selected == 'all':
        raise HTTPException(400, '请选择一个 Profile 查看和取消待执行步骤')
    jobs = cron._call_cron_for_profile(selected, 'list_jobs', True)
    with cron._owner_home_scope(selected):
        return {'jobs': list_upcoming(jobs), 'profile': selected}


def cancel_upcoming(job_id, body, profile=None):
    from . import cron
    from cron.upcoming import cancel
    selected = cron._job_profile(job_id, profile)
    job = cron._found(cron._call_cron_for_profile(selected, 'get_job', job_id))
    with cron._owner_home_scope(selected):
        try:
            return cancel(job, body.get('instant'), body.get('plan'))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
