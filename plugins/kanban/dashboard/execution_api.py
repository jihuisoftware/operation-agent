"""Private execution settings for one board; Profile credentials remain request-scoped."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StrictBool

from hermes_cli import kanban_db_connect as kbc, kanban_execution as execution

router = APIRouter()


class ExecutionBody(BaseModel):
    enabled: StrictBool
    expected_revision: int = Field(ge=0, strict=True)


def status(conn):
    from hermes_cli.kanban import _check_dispatcher_presence
    from hermes_constants import get_hermes_home
    running, detail = _check_dispatcher_presence(hermes_home=get_hermes_home())
    return {**execution.read(conn), 'dispatcher_running': bool(running), 'dispatcher_detail': detail,
            'running': conn.execute("SELECT count(*) FROM tasks WHERE status='running'").fetchone()[0]}


def board_slug(slug):
    from hermes_cli import kanban_db as kb
    try:
        slug = kb._normalize_board_slug(slug)
        if slug != kb.DEFAULT_BOARD and not kb.board_exists(slug):
            raise HTTPException(404, '看板不存在')
        return slug
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('/boards/{slug}/execution')
def get_execution(slug: str):
    with kbc.connect_closing(board=board_slug(slug)) as conn:
        return {**status(conn), 'board': board_slug(slug)}


@router.put('/boards/{slug}/execution')
def set_execution(slug: str, body: ExecutionBody):
    try:
        with kbc.connect_closing(board=board_slug(slug)) as conn:
            execution.update(conn, enabled=body.enabled, expected_revision=body.expected_revision)
            return {**status(conn), 'board': board_slug(slug)}
    except execution.ExecutionConflict as exc:
        raise HTTPException(409, str(exc)) from exc


def initialize_task_column(conn, task_id, column):
    """Called within the creation transaction; a new task is never momentarily runnable."""
    from hermes_cli import kanban_db as kb
    if column == 'ready' and not kb._parents_satisfied(conn, task_id):
        raise HTTPException(409, '依赖尚未完成，不能进入待执行')
    conn.execute('UPDATE tasks SET status=? WHERE id=?', (column, task_id))
    kb._append_event(conn, task_id, 'blocked' if column == 'blocked' else 'status',
                     {'status': column, 'reason': '人工创建', 'kind': 'needs_input'})
