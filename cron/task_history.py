"""Durable task plans, per-execution steps and outputs beside the Cron attempt ledger."""
from contextlib import contextmanager
import hashlib
import json
import os

from hermes_time import now

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS task_definitions (job_id TEXT PRIMARY KEY, data TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS task_plans (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, data TEXT NOT NULL, created TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS task_runs (execution_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, plan_id TEXT NOT NULL, context TEXT NOT NULL DEFAULT '{}', output TEXT, updated TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS task_steps (execution_id TEXT NOT NULL, id TEXT NOT NULL, title TEXT NOT NULL, intent TEXT NOT NULL, state TEXT NOT NULL, detail TEXT NOT NULL, updated TEXT NOT NULL, PRIMARY KEY(execution_id,id))",
    "CREATE TABLE IF NOT EXISTS task_events (id INTEGER PRIMARY KEY, execution_id TEXT NOT NULL, step_id TEXT NOT NULL, detail TEXT NOT NULL, data TEXT NOT NULL, created TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS task_events_execution ON task_events(execution_id,id)",
    """CREATE TRIGGER IF NOT EXISTS task_history_terminal AFTER UPDATE OF status ON executions
       WHEN NEW.status IN ('completed','failed','unknown') BEGIN
       UPDATE task_steps SET state=CASE state WHEN 'running' THEN 'interrupted' ELSE 'not_run' END,
          updated=NEW.finished_at WHERE execution_id=NEW.id AND state IN ('running','pending');
       UPDATE task_runs SET updated=NEW.finished_at WHERE execution_id=NEW.id;
       END""",
    """CREATE TRIGGER IF NOT EXISTS task_history_prune AFTER DELETE ON executions BEGIN
       DELETE FROM task_events WHERE execution_id=OLD.id;
       DELETE FROM task_steps WHERE execution_id=OLD.id;
       DELETE FROM task_runs WHERE execution_id=OLD.id;
       DELETE FROM task_plans WHERE job_id=OLD.job_id AND id NOT IN (SELECT plan_id FROM task_runs);
       END""",
)
PLAN_FIELDS = ('id', 'name', 'prompt', 'script', 'no_agent', 'schedule', 'skills', 'model', 'provider', 'workdir', 'deliver')


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


@contextmanager
def connection():
    from cron.executions import _transaction
    with _transaction() as db:
        for statement in SCHEMA:
            db.execute(statement)
        yield db


def _save_plan(db, job):
    data = {k: job.get(k) for k in PLAN_FIELDS}
    definition = db.execute('SELECT data FROM task_definitions WHERE job_id=?', (job['id'],)).fetchone()
    if definition:
        data['definition'] = json.loads(definition[0])
    identity = hashlib.sha256(encoded(data).encode()).hexdigest()
    db.execute('INSERT OR IGNORE INTO task_plans VALUES (?,?,?,?)', (identity, job['id'], encoded(data), now().isoformat()))
    return identity


def define(job_id, definition):
    """A plugin supplies its current business plan without coupling Cron to that plugin."""
    with connection() as db:
        db.execute('INSERT INTO task_definitions VALUES (?,?) ON CONFLICT(job_id) DO UPDATE SET data=excluded.data '
                   'WHERE task_definitions.data != excluded.data', (job_id, encoded(definition)))


def begin(execution_id, job):
    with connection() as db:
        plan = _save_plan(db, job)
        db.execute('INSERT OR IGNORE INTO task_runs(execution_id,job_id,plan_id,updated) VALUES (?,?,?,?)',
                   (execution_id, job['id'], plan, now().isoformat()))


def capture(execution_id, job_id):
    from cron.jobs import get_job
    begin(execution_id, get_job(job_id) or {'id': job_id})


def save_current_output(job_id, output):
    from cron.execution_identity import current_cron_execution
    execution = current_cron_execution()
    if execution and execution.job_id == job_id:
        save_output(execution.execution_id, output)


def _writable(db, execution_id):
    from cron.executions import _owner_is_live
    row = db.execute("SELECT status,pid,process_started_at FROM executions WHERE id=?", (execution_id,)).fetchone()
    return (row and row['status'] in {'claimed', 'running'} and row['pid'] in {os.getpid(), os.getppid()}
            and _owner_is_live(row['pid'], row['process_started_at']))


def declare(execution_id, steps, context):
    stamp = now().isoformat()
    with connection() as db:
        if not _writable(db, execution_id):
            return
        db.execute('UPDATE task_runs SET context=?,updated=? WHERE execution_id=?', (encoded(context), stamp, execution_id))
        for step in steps:
            db.execute('INSERT OR IGNORE INTO task_steps VALUES (?,?,?,?,?,?,?)',
                       (execution_id, step['id'], step['title'], step['intent'], step.get('state', 'pending'), step.get('detail', ''), stamp))


def progress(execution_id, step_id, *, state, detail, data=None):
    stamp = now().isoformat()
    with connection() as db:
        if not _writable(db, execution_id):
            return
        changed = db.execute('UPDATE task_steps SET state=?,detail=?,updated=? WHERE execution_id=? AND id=?',
                             (state, detail, stamp, execution_id, step_id)).rowcount
        if not changed:
            return
        db.execute('INSERT INTO task_events(execution_id,step_id,detail,data,created) VALUES (?,?,?,?,?)',
                   (execution_id, step_id, detail, encoded(data or {}), stamp))
        db.execute('UPDATE task_runs SET updated=? WHERE execution_id=?', (stamp, execution_id))


def save_output(execution_id, output):
    with connection() as db:
        if _writable(db, execution_id):
            db.execute('UPDATE task_runs SET output=?,updated=? WHERE execution_id=?', (output, now().isoformat(), execution_id))


def cancel_pending_step(execution_id, step_id, reason):
    """Called after a task owner atomically cancels its durable, not-yet-started work."""
    stamp = now().isoformat()
    with connection() as db:
        changed = db.execute("UPDATE task_steps SET state='cancelled',detail=?,updated=? WHERE execution_id=? AND id=? "
                             "AND state IN ('pending','not_due','not_run')", (reason, stamp, execution_id, step_id)).rowcount
        if changed:
            db.execute('INSERT INTO task_events(execution_id,step_id,detail,data,created) VALUES (?,?,?,?,?)',
                       (execution_id, step_id, reason, '{}', stamp))
            db.execute('UPDATE task_runs SET updated=? WHERE execution_id=?', (stamp, execution_id))


def detail(job, execution_id=None):
    from cron.executions import get_execution, list_executions, live_inflight_execution
    attempts = list_executions(job_id=job['id'], limit=50)
    active = live_inflight_execution(job['id'])
    selected = get_execution(execution_id) if execution_id else active or next(iter(attempts), None)
    if execution_id and (selected is None or selected['job_id'] != job['id']):
        raise LookupError('运行记录不属于此任务或已清理')
    with connection() as db:
        plan_id = _save_plan(db, job)
        current = json.loads(db.execute('SELECT data FROM task_plans WHERE id=?', (plan_id,)).fetchone()[0])
        record = db.execute('SELECT * FROM task_runs WHERE execution_id=? AND job_id=?', (selected['id'], job['id'])).fetchone() if selected else None
        snapshot = json.loads(db.execute('SELECT data FROM task_plans WHERE id=?', (record['plan_id'],)).fetchone()[0]) if record else None
        steps = [dict(r) for r in db.execute('SELECT * FROM task_steps WHERE execution_id=? ORDER BY rowid', (selected['id'],))] if selected else []
        events = [dict(r) for r in db.execute('SELECT * FROM task_events WHERE execution_id=? ORDER BY id DESC', (selected['id'],))] if selected else []
    return {'plan': current, 'attempts': attempts, 'execution': selected, 'snapshot': snapshot,
            'context': json.loads(record['context']) if record else {}, 'steps': steps,
            'events': [{**e, 'data': json.loads(e['data'])} for e in events],
            'output': record['output'] if record else None, 'updated': record['updated'] if record else None}
