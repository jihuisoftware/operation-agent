"""Durable account interlocks and resumable batch interruptions, independent of plan pause."""
import json
import time

from .policy import local_day, now_iso
from .store import encoded

CODES = {'AUTH_REQUIRED', 'VERIFICATION_REQUIRED', 'ACCOUNT_CHANGED', 'BROWSER_UNAVAILABLE', 'COMMAND_EXPIRED', 'SYSTEM_SUSPENDED'}


def needs_account(policy, stage=None):
    from .modules import ACTION_MODULE
    return any(policy['allowed'][kind] and policy['modules'][module] and (stage is None or stage == module)
               for kind, module in ACTION_MODULE.items())


class ExecutionPaused(RuntimeError):
    def __init__(self, result):
        self.result = result
        super().__init__(result.get('error', '网页执行已暂停，请检查账号后手动继续'))


def account_key(store, db=None):
    if not store.workspace:
        return 'local'
    if db is None:
        with store.connection() as connection:
            return account_key(store, connection)
    return db.execute('SELECT account FROM directory.businesses WHERE id=?', (store.scope['business_id'],)).fetchone()[0]


def block(store, db=None):
    if db is None:
        with store.connection() as connection:
            return block(store, connection)
    key = 'execution-block:' + account_key(store, db)
    row = (db.execute('SELECT data FROM directory.preferences WHERE id=?', (key,)).fetchone() if store.workspace
           else db.execute("SELECT data FROM objects WHERE id=? AND kind='execution_block'", (key,)).fetchone())
    data = json.loads(row[0]) if row else None
    return data if data and data.get('active') else None


def set_block(store, db, result):
    key = 'execution-block:' + account_key(store, db)
    previous = block(store, db)
    data = {**result, 'active': True, 'at': now_iso(), 'cause_at': result.get('cause_at', time.time()),
            'revision': (previous or {}).get('revision', 0) + 1}
    if store.workspace:
        db.execute('INSERT OR REPLACE INTO directory.preferences VALUES (?,?)', (key, encoded(data)))
    else:
        db.execute("INSERT OR REPLACE INTO objects VALUES (?,'execution_block',?,?)", (key, encoded(data), now_iso()))
    return data


def clear_block(store, db):
    key = 'execution-block:' + account_key(store, db)
    previous = block(store, db)
    if previous:
        clearance = {'at': time.time(), 'cause_command_id': previous.get('cause_command_id')}
        clearance_key = 'execution-clear:' + account_key(store, db)
        if store.workspace:
            db.execute('INSERT OR REPLACE INTO directory.preferences VALUES (?,?)', (clearance_key, encoded(clearance)))
        else:
            db.execute("INSERT OR REPLACE INTO objects VALUES (?, 'execution_clear', ?, ?)", (clearance_key, encoded(clearance), now_iso()))
    if store.workspace:
        db.execute('DELETE FROM directory.preferences WHERE id=?', (key,))
    else:
        db.execute("DELETE FROM objects WHERE id=? AND kind='execution_block'", (key,))


def identity(store, payload=None):
    if payload is not None:
        if payload.get('resume_key'):
            return payload['resume_key']
        batch = payload.get('manual_run_id')
    else:
        if getattr(store, 'resume_key', None):
            return store.resume_key
        batch = store.manual_run_id
    if batch:
        return batch if batch.startswith(('debug:', 'manual:', 'quick:')) else 'manual:' + batch
    return payload.get('run_id') if payload is not None else store.current_run_id


def load(store, key, db=None):
    if not key:
        return None
    if db is None:
        with store.connection() as connection:
            return load(store, key, connection)
    row = db.execute("SELECT data FROM objects WHERE id=? AND kind='execution_pause'", ('execution-pause:' + key,)).fetchone()
    return json.loads(row[0]) if row else None


def save(store, db, key, result, payload=None):
    if not key:
        return None
    payload = payload or {}
    prior = load(store, key, db)
    if prior and prior['state'] == 'paused':
        if result.get('error_code') == 'SYSTEM_SUSPENDED' and prior['error_code'] == 'COMMAND_EXPIRED':
            from .pause_origin import FIELDS
            prior.update({k: result[k] for k in FIELDS if k in result})
            prior.update(error_code=result['error_code'], error=result['error'])
            db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(prior), 'execution-pause:' + key))
        return prior
    settings = db.execute('SELECT version,data FROM settings WHERE id=1').fetchone()
    policy = json.loads(settings['data'])
    run_id = payload.get('run_id') or store.current_run_id
    run = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
    account = payload.get('account_id') or policy['account_id']
    if not account and store.workspace:
        account = db.execute('SELECT identity FROM directory.accounts WHERE id=?', (account_key(store, db),)).fetchone()[0]
    data = {**(prior or {}), 'id': key, 'state': 'paused', 'revision': (prior or {}).get('revision', 0) + 1,
            'attempt': (prior or {}).get('attempt', 0), 'version': run['version'] if run else settings['version'],
            'day': run['day'] if run else local_day(policy), 'account_link': account_key(store, db), 'account_id': account,
            'run_id': run_id, 'stage': run['stage'] if run else None, 'slot': run['slot'] if run else None,
            'error_code': result['error_code'], 'error': result['error'], 'paused_at': now_iso(),
            **({'cause_at': result['cause_at']} if 'cause_at' in result else {})}
    from .pause_origin import FIELDS
    data.update({k: result[k] for k in FIELDS if k in result})
    data['inherited'] = bool(result.get('cause_run_id') and result['cause_run_id'] != run_id)
    from .resume_artifacts import capture
    batch = key.removeprefix('manual:') if key.startswith(('debug:', 'manual:', 'quick:')) else None
    data['artifacts'] = capture(store, db, data['day'], policy, (prior or {}).get('artifacts'), batch=batch)
    db.execute("INSERT OR REPLACE INTO objects VALUES (?,'execution_pause',?,?)", ('execution-pause:' + key, encoded(data), now_iso()))
    return data


def pause(store, result, *, db=None, payload=None):
    if db is None:
        with store.connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            return pause(store, result, db=connection, payload=payload)
    from .pause_origin import enrich
    result = set_block(store, db, enrich(store, db, result, payload))
    key = identity(store, payload)
    saved = save(store, db, key, result, payload)
    if key:
        cancel_pending(store, db, key, result)
    return saved


def cancel_pending(store, db, key, result):
    for row in db.execute("SELECT * FROM commands WHERE state='queued'").fetchall():
        payload = json.loads(row['payload'])
        if payload.get('resume_probe') or row['kind'] == 'verify' or identity(store, payload) != key:
            continue
        stopped = {**result, 'state': 'blocked', 'submitted': False, 'dispatch_state': 'not_started'}
        db.execute("UPDATE commands SET state='interrupted',result=? WHERE id=?", (encoded(stopped), row['id']))
        if row['action_id']:
            db.execute("UPDATE actions SET state='blocked',result=? WHERE id=? AND state='queued'", (encoded(stopped), row['action_id']))


def guard(store, *, web=False, db=None):
    from .batch_cancellation import check
    check(store, db=db)
    paused = load(store, identity(store), db)
    reason = paused if paused and paused['state'] == 'paused' else None
    if web:
        reason = reason or block(store, db)
    if reason:
        propagate(store, reason, db)
        from .execution_pause_view import describe
        local = load(store, identity(store), db) or reason
        raise ExecutionPaused({**reason, 'error': describe(store, local, db)['error']})


def propagate(store, reason, db=None):
    """A guard observing a prior failure must not invent a new failure timestamp or epoch."""
    if db is None:
        with store.connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            return propagate(store, reason, connection)
    key = identity(store)
    save(store, db, key, reason)
    if key:
        cancel_pending(store, db, key, reason)


def observe(store, body):
    if body['platform'] != 'xiaohongshu':
        return
    code = {'logged_out': 'AUTH_REQUIRED', 'verification': 'VERIFICATION_REQUIRED'}.get(body['state'])
    if body['state'] == 'logged_in':
        expected = store.policy()[1]['account_id']
        if store.workspace:
            with store.connection() as db:
                expected = db.execute('SELECT identity FROM directory.accounts WHERE id=?', (account_key(store, db),)).fetchone()[0] or expected
        if expected and expected != body.get('account_id'):
            code = 'ACCOUNT_CHANGED'
    if code:
        message = {'AUTH_REQUIRED': '账号已退出，请重新登录后手动继续',
                   'VERIFICATION_REQUIRED': '账号需要安全验证，请处理后手动继续',
                   'ACCOUNT_CHANGED': '当前账号已变化，请切回原账号后继续'}[code]
        pause(store, {'error_code': code, 'error': message, 'interruption_scope': 'batch'})
