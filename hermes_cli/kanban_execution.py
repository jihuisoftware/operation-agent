"""Board-owned automatic dispatch permission, checked inside the task claim transaction."""
from contextlib import contextmanager
from contextvars import ContextVar
import sqlite3
import time
from typing import Optional

EXECUTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS kanban_execution_settings (
    id INTEGER PRIMARY KEY CHECK(id=1),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
    revision INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER
);
"""
_automatic = ContextVar('kanban_automatic_dispatch', default=False)


class ExecutionConflict(ValueError):
    pass


def read(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='kanban_execution_settings'").fetchone():
        return {'enabled': False, 'revision': 0, 'updated_at': None}
    row = conn.execute('SELECT enabled,revision,updated_at FROM kanban_execution_settings WHERE id=1').fetchone()
    return {'enabled': bool(row[0]), 'revision': row[1], 'updated_at': row[2]} if row else {
        'enabled': False, 'revision': 0, 'updated_at': None}


def update(conn, *, enabled, expected_revision):
    from hermes_cli import kanban_db as kb
    kb._assert_not_delegated_child_mutation()
    if type(enabled) is not bool or type(expected_revision) is not int or expected_revision < 0:
        raise ValueError('执行设置格式无效')
    with kb.write_txn(conn):
        current = read(conn)
        if current['revision'] != expected_revision:
            raise ExecutionConflict('看板执行设置已在其他窗口修改，请刷新后重试')
        conn.execute(EXECUTION_SCHEMA)
        conn.execute('INSERT OR REPLACE INTO kanban_execution_settings VALUES (1,?,?,?)',
                     (int(enabled), expected_revision + 1, int(time.time())))
        return read(conn)


def claim_allowed(conn):
    return not _automatic.get() or read(conn)['enabled']


@contextmanager
def dispatch_scope(automatic):
    """Serialize host-wide capacity decisions across boards and bind this tick's mode."""
    from hermes_cli import kanban_db as kb, kanban_db_connect as kbc
    token = _automatic.set(automatic)
    try:
        with kbc._dispatch_tick_lock(kb.kanban_home() / '.kanban-host-capacity') as held:
            yield held
    finally:
        _automatic.reset(token)


def claim_and_open_run(
    conn: sqlite3.Connection, task_id: str, source_status: str, lock: str, expires: int, now: int,
    *, event_extra: Optional[dict] = None,
) -> Optional[int]:
    """CAS ``source_status -> running``, open a run row, emit ``claimed``; None
    when the CAS lost. Caller holds the txn."""
    if not claim_allowed(conn):
        return None
    cur = conn.execute(
        f"""
        UPDATE tasks
           SET status        = 'running',
               claim_lock    = ?,
               claim_expires = ?,
               started_at    = COALESCE(started_at, ?)
         WHERE id = ?
           AND status = '{source_status}'
           AND claim_lock IS NULL
        """,
        (lock, expires, now, task_id),
    )
    if cur.rowcount != 1:
        return None
    trow = conn.execute(
        "SELECT assignee, max_runtime_seconds, current_step_key "
        "FROM tasks WHERE id = ?", (task_id,),
    ).fetchone()
    run_cur = conn.execute(
        """
        INSERT INTO task_runs (
            task_id, profile, step_key, status,
            claim_lock, claim_expires, max_runtime_seconds,
            started_at
        ) VALUES (?, ?, ?, 'running', ?, ?, ?, ?)
        """,
        (
            task_id, trow["assignee"] if trow else None, trow["current_step_key"] if trow else None,
            lock, expires, trow["max_runtime_seconds"] if trow else None, now,
        ),
    )
    run_id = run_cur.lastrowid
    conn.execute("UPDATE tasks SET current_run_id = ? WHERE id = ?", (run_id, task_id))
    from hermes_cli import kanban_db as kb
    kb._append_event(
        conn, task_id, "claimed",
        {"lock": lock, "expires": expires, "run_id": run_id, **(event_extra or {})}, run_id=run_id,
    )
    return run_id



def reclaim(conn, task_id, *, reason=None, signal_fn=None):
    """An operator reclaim must prove the worker and admitted interpreter stopped."""
    from hermes_cli import kanban_db as kb
    row = conn.execute(
        "SELECT status, claim_lock, worker_pid, worker_started_at FROM tasks WHERE id = ?", (task_id,),
    ).fetchone()
    if not row:
        return False
    if row["status"] != "running" and row["claim_lock"] is None:
        # Nothing to reclaim — already ready / blocked / done.
        return False
    prev_lock = row["claim_lock"]
    termination = kb._terminate_reclaimed_worker(
        row["worker_pid"], prev_lock, signal_fn=signal_fn, started_at=row["worker_started_at"])
    from hermes_cli.kanban_owner_recovery import owner_reclaim_blocked_after_kill
    if termination.get('prev_pid') and not termination.get('terminated'):
        return False
    with kb.write_txn(conn):
        if owner_reclaim_blocked_after_kill(conn, task_id, signalled=bool(termination.get('termination_attempted'))):
            return False
        retry_status = kb._retry_status_for_run(conn, task_id)
        cur = conn.execute(
            "UPDATE tasks SET status = ?, claim_lock = NULL, "
            "claim_expires = NULL, worker_pid = NULL, worker_started_at = NULL "
            "WHERE id = ? AND status IN ('running', 'ready', 'blocked') "
            "AND claim_lock IS ?", (retry_status, task_id, prev_lock),
        )
        if cur.rowcount != 1:
            return False
        kb._record_reclaim(
            conn, task_id, termination,
            error=f"manual_reclaim: {reason}" if reason else f"manual_reclaim lock={prev_lock}",
            payload={"manual": True, "reason": reason, "prev_lock": prev_lock, "retry_status": retry_status},
        )
    # Operator intervention = fresh retry budget (own txn, runs after commit).
    kb._clear_failure_counter(conn, task_id)
    return True


def stop_run(conn, task_id, run_id, *, reason=None):
    """Stop one exact attempt and park it; never requeue under the automatic dispatcher."""
    from hermes_cli import kanban_db as kb
    with dispatch_scope(False) as held:
        task = kb.get_task(conn, task_id)
        if not held or task is None or task.current_run_id != run_id or task.status != 'running':
            return False
        if not kb.reclaim_task(conn, task_id, reason=reason or '用户停止执行'):
            return False
        with kb.write_txn(conn):
            conn.execute("UPDATE tasks SET status='blocked',block_kind='needs_input' WHERE id=? AND status IN ('ready','review') AND claim_lock IS NULL", (task_id,))
            kb._append_event(conn, task_id, 'blocked', {'reason': reason or '用户停止执行', 'kind': 'needs_input', 'manual': True}, run_id=run_id)
        return True
