"""Profile-owned, per-attempt usage. No prompts, credentials or response text are stored."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict
import logging
import os
from pathlib import Path
import sqlite3
import time
import uuid

from hermes_constants import get_hermes_home

log = logging.getLogger(__name__)
CONTEXT = ContextVar('token_usage_context', default=None)
LAST_CALL = ContextVar('token_usage_last_call', default=None)
TOKEN_USAGE_SCHEMA_VERSION = 2
RECOVERY_INTERVAL_SECONDS = 30.0
FIELDS = ('business_id', 'topic_id', 'run_id', 'stage', 'session_id', 'turn_id', 'task_name')
TOKENS = ('input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens', 'reasoning_tokens', 'prompt_tokens', 'total_tokens')
SCHEMA = """
CREATE TABLE IF NOT EXISTS token_usage_meta(
 id INTEGER PRIMARY KEY CHECK(id=1), since REAL NOT NULL,
 schema_version INTEGER NOT NULL DEFAULT 1, last_recovery REAL);
CREATE TABLE IF NOT EXISTS token_usage_tasks(
 id TEXT PRIMARY KEY, business_id TEXT NOT NULL DEFAULT '', topic_id TEXT NOT NULL DEFAULT '',
 run_id TEXT NOT NULL DEFAULT '', stage TEXT NOT NULL DEFAULT '', session_id TEXT NOT NULL DEFAULT '',
 turn_id TEXT NOT NULL DEFAULT '', task_name TEXT NOT NULL DEFAULT '', state TEXT NOT NULL,
 started REAL NOT NULL, ended REAL, pid INTEGER NOT NULL, process_started REAL NOT NULL);
CREATE TABLE IF NOT EXISTS token_usage_calls(
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES token_usage_tasks(id), purpose TEXT NOT NULL,
 model TEXT NOT NULL, provider TEXT NOT NULL, started REAL NOT NULL, received REAL,
 state TEXT NOT NULL, error_type TEXT NOT NULL DEFAULT '',
 input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER, cache_write_tokens INTEGER,
 reasoning_tokens INTEGER, prompt_tokens INTEGER, total_tokens INTEGER);
CREATE INDEX IF NOT EXISTS token_usage_time ON token_usage_calls(received,id);
CREATE INDEX IF NOT EXISTS token_usage_task ON token_usage_calls(task_id,received,id);
CREATE INDEX IF NOT EXISTS token_usage_scope ON token_usage_tasks(business_id,topic_id,stage);
CREATE INDEX IF NOT EXISTS token_usage_active ON token_usage_tasks(state);
"""


def _ensure_schema(db) -> None:
    """Upgrade the profile ledger without rewriting existing receipts."""
    columns = {row[1] for row in db.execute('PRAGMA table_info(token_usage_meta)')}
    if 'schema_version' not in columns:
        db.execute('ALTER TABLE token_usage_meta ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 1')
    if 'last_recovery' not in columns:
        db.execute('ALTER TABLE token_usage_meta ADD COLUMN last_recovery REAL')
    version = db.execute('SELECT schema_version FROM token_usage_meta WHERE id=1').fetchone()
    current = int(version[0]) if version else 1
    if current < 2:
        db.execute('CREATE INDEX IF NOT EXISTS token_usage_model ON token_usage_calls(model,received,id)')
        db.execute('CREATE INDEX IF NOT EXISTS token_usage_provider ON token_usage_calls(provider,received,id)')
        db.execute('CREATE INDEX IF NOT EXISTS token_usage_purpose ON token_usage_calls(purpose,received,id)')
        db.execute('UPDATE token_usage_meta SET schema_version=? WHERE id=1', (TOKEN_USAGE_SCHEMA_VERSION,))


@contextmanager
def connection(path=None):
    path = Path(path) if path else get_hermes_home() / 'state.db'
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.executescript(SCHEMA)
        _ensure_schema(db)
        db.execute('INSERT OR IGNORE INTO token_usage_meta(id,since,schema_version) VALUES(?,?,?)',
                   (1, time.time(), TOKEN_USAGE_SCHEMA_VERSION))
        db.commit()
        with db:
            yield db
    finally:
        db.close()


def start_task(identity, *, path=None, **scope):
    import psutil
    path = str(path or get_hermes_home() / 'state.db')
    with connection(path) as db:
        db.execute('INSERT OR IGNORE INTO token_usage_tasks VALUES (?,?,?,?,?,?,?,?,?,?,NULL,?,?)',
                   (identity, *(str(scope.get(k) or '') for k in FIELDS), 'running', time.time(),
                    os.getpid(), psutil.Process().create_time()))
    return {'path': path, 'task_id': identity, **scope}


def finish_task(context, state='completed'):
    with connection(context['path']) as db:
        db.execute("UPDATE token_usage_tasks SET state=?,ended=? WHERE id=? AND state='running'",
                   (state, time.time(), context['task_id']))
        db.execute("UPDATE token_usage_calls SET state='interrupted',error_type='TaskEnded',received=? WHERE task_id=? AND state='running'",
                   (time.time(), context['task_id']))


@contextmanager
def bind(context):
    token = CONTEXT.set(context)
    try:
        yield context
    finally:
        CONTEXT.reset(token)


def recover(db):
    """A dead process cannot later provide a receipt. PID reuse is checked as well."""
    import psutil
    for row in db.execute("SELECT DISTINCT pid,process_started FROM token_usage_tasks WHERE state='running'").fetchall():
        try:
            alive = abs(psutil.Process(row['pid']).create_time() - row['process_started']) < 0.01
        except psutil.NoSuchProcess:
            alive = False
        except psutil.AccessDenied:
            continue
        if not alive:
            db.execute("UPDATE token_usage_calls SET state='interrupted',received=?,error_type='ProcessEnded' WHERE state='running' AND task_id IN (SELECT id FROM token_usage_tasks WHERE pid=? AND process_started=? AND state='running')", (time.time(), *row))
            db.execute("UPDATE token_usage_tasks SET state='interrupted',ended=? WHERE state='running' AND pid=? AND process_started=?", (time.time(), *row))


def recover_if_due(db, *, now=None, interval=RECOVERY_INTERVAL_SECONDS) -> bool:
    """Recover abandoned work at most once per interval for read-heavy callers."""
    now = time.time() if now is None else now
    row = db.execute('SELECT last_recovery FROM token_usage_meta WHERE id=1').fetchone()
    last = row[0] if row else None
    if last is not None and now - last < interval:
        return False
    recover(db)
    db.execute('UPDATE token_usage_meta SET last_recovery=? WHERE id=1', (now,))
    return True


class Attempt:
    def __init__(self, *, model='', provider='', purpose='', context=None, api_mode=None, scope=None):
        self.id = uuid.uuid4().hex
        self.api_mode = api_mode
        self.provider = provider
        self.own_task = not (context or CONTEXT.get())
        self.context = context or CONTEXT.get() or start_task(self.id, task_name=purpose or '辅助调用', **(scope or {}))
        with connection(self.context['path']) as db:
            db.execute("INSERT INTO token_usage_calls(id,task_id,purpose,model,provider,started,state) VALUES(?,?,?,?,?,?,'running')",
                       (self.id, self.context['task_id'], purpose, model, provider, time.time()))

    def finish(self, response=None, error=None, normalized=None):
        from agent.usage_pricing import normalize_usage
        raw = response.get('usage') if isinstance(response, dict) else getattr(response, 'usage', None)
        values = normalized
        if values is None and raw is not None:
            usage = normalize_usage(raw, provider=self.provider, api_mode=self.api_mode)
            values = {**asdict(usage), 'prompt_tokens': usage.prompt_tokens, 'total_tokens': usage.total_tokens}
        state = 'confirmed' if values is not None else 'failed' if error else 'unknown'
        model = response.get('model') if isinstance(response, dict) else getattr(response, 'model', None)
        with connection(self.context['path']) as db:
            db.execute(f"UPDATE token_usage_calls SET state=?,received=?,error_type=?,model=COALESCE(NULLIF(?,''),model),{','.join(k+'=?' for k in TOKENS)} WHERE id=? AND state='running'",
                       (state, time.time(), type(error).__name__ if error else '', str(model or ''),
                        *(max(0, int(values.get(k, 0))) if values is not None else None for k in TOKENS), self.id))
        if self.own_task:
            finish_task(self.context, 'failed' if error else 'completed')


def safe_start(**kwargs):
    try:
        return Attempt(**kwargs)
    except Exception:
        log.exception('Token usage recording could not start')
        return None


def safe_finish(attempt, **kwargs):
    if attempt is not None:
        try:
            attempt.finish(**kwargs)
            LAST_CALL.set(attempt.id)
        except Exception:
            log.exception('Token usage receipt could not be saved')
