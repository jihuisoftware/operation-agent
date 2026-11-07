"""Replay a durable desktop interruption, without replacing an accepted or human result."""
import json
import math

from .policy import now_iso
from .store import encoded


def _settled(store, db, row):
    from .execution_pause import account_key, identity, load
    pause = load(store, identity(store, json.loads(row['payload'])), db)
    if pause and pause['state'] not in {'paused', 'running'}:
        return True
    key = 'execution-clear:' + account_key(store, db)
    cleared = (db.execute('SELECT data FROM directory.preferences WHERE id=?', (key,)).fetchone() if store.workspace
               else db.execute("SELECT data FROM objects WHERE id=? AND kind='execution_clear'", (key,)).fetchone())
    clearance = json.loads(cleared[0]) if cleared else {}
    if clearance.get('at', 0) >= row['expires'] or clearance.get('cause_command_id') == row['id']:
        return True
    action = db.execute('SELECT state,result FROM actions WHERE id=?', (row['action_id'],)).fetchone() if row['action_id'] else None
    return row['state'] in {'done', 'cancelled'} or (action and (
        action['state'] in {'published', 'confirmed'} or json.loads(action['result']).get('manual_verification')))


def accept(store, body):
    identity, worker, result = body['id'], body['worker'], body['result']
    if result.get('error_code') not in {'SYSTEM_SUSPENDED', 'BROWSER_UNAVAILABLE'}:
        raise ValueError('中断原因无效')
    if result.get('dispatch_state') not in {'not_started', 'read_only', 'submission_started'}:
        raise ValueError('中断阶段无效')
    epoch = result.get('power_epoch')
    if not isinstance(epoch, str) or not 1 <= len(epoch) <= 160:
        raise ValueError('中断代次无效')
    for key in ('sleep_started_at', 'sleep_resumed_at'):
        if key in result and (type(result[key]) not in {int, float} or not math.isfinite(result[key])):
            raise ValueError('电源事件时间无效')
    uncertain = result['dispatch_state'] == 'submission_started'
    result = {**result, 'state': 'unknown' if uncertain else 'blocked', 'submitted': uncertain}
    with store.connection() as db:
        row = db.execute('SELECT * FROM commands WHERE id=? AND worker=?', (identity, worker)).fetchone()
        if not row:
            raise ValueError('中断记录不属于此执行器')
        record = {'command_id': identity, 'worker': worker, 'result': result, 'at': now_iso()}
        db.execute("INSERT OR IGNORE INTO objects VALUES (?, 'power_interruption', ?, ?)",
                   ('power-interruption:' + identity + ':' + epoch, encoded(record), record['at']))
        final = _settled(store, db, row)
    if not final:
        try:
            store.acknowledge(identity, worker, result)
        except ValueError:
            with store.connection() as db:
                current = db.execute('SELECT * FROM commands WHERE id=?', (identity,)).fetchone()
                settled = _settled(store, db, current)
            if not settled:
                raise
    return {'ok': True}
