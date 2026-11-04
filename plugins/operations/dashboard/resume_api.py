"""Private continuation entry points; login alone never resumes side effects."""
from fastapi import APIRouter, HTTPException

from ..store import Store
from ..execution_pause import ExecutionPaused

router = APIRouter()


@router.get('/runs/paused')
def paused_runs():
    from ..execution_resume import paused_runs as read
    return {'runs': [row for row in read(Store()) if not row['id'].startswith('debug:')]}


@router.post('/runs/{identity}/resume')
def resume(identity: str, body: dict):
    from ..runtime_resume import resume as continue_run
    try:
        return continue_run(identity, body)
    except (ValueError, KeyError, ExecutionPaused) as exc:
        raise HTTPException(409, str(exc)) from exc
