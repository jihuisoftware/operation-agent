"""Profile-scoped persisted plan and live execution detail for the Desktop."""
from fastapi import HTTPException


def read_detail(job_id, profile=None, execution_id=None):
    from . import cron
    from cron.task_history import detail
    selected = cron._job_profile(job_id, profile)
    job = cron._found(cron._call_cron_for_profile(selected, 'get_job', job_id))
    with cron._owner_home_scope(selected):
        try:
            return {**detail(job, execution_id), 'profile': selected}
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
