"""Private continuation entry points; login alone never resumes side effects."""
from fastapi import APIRouter, HTTPException

from ..store import Store
from ..execution_pause import ExecutionPaused

router = APIRouter()


@router.get('/runs/{identity}/detail')
def run_detail(identity: str):
    from ..execution_pause import load
    from ..execution_pause_view import describe
    store = Store()
    with store.connection() as db:
        row = db.execute('SELECT id,stage,started,state,detail FROM runs WHERE id=?', (identity,)).fetchone()
    if not row:
        raise HTTPException(404, '原始任务不存在或不属于当前主题')
    return {**dict(row), 'pause': describe(store, load(store, identity))}


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
