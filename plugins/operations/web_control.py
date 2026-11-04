"""Manual takeover is a renewable window lease, not a permanent account flag."""
from datetime import datetime
import json
import time

HOLD_TTL = 15


def account_state(db, account, prefix='directory.'):
    cutoff = time.time() - HOLD_TTL
    db.execute(f'DELETE FROM {prefix}account_holds WHERE account_id=? AND seen<=?', (account, cutoff))
    db.execute(f'UPDATE {prefix}accounts SET held=0 WHERE id=? AND held!=0 AND NOT EXISTS '
               f'(SELECT 1 FROM {prefix}account_holds WHERE account_id=?)', (account, account))
    row = db.execute(f'SELECT a.held,a.conflict,h.worker FROM {prefix}accounts a '
                     f'LEFT JOIN {prefix}account_holds h ON h.account_id=a.id WHERE a.id=?', (account,)).fetchone()
    return {'held': bool(row['held']), 'worker': row['worker'], 'conflict': row['conflict']}


def account_heartbeat(db, account, worker, takeover=None, prefix='directory.'):
    if takeover is not False:
        db.execute(f'UPDATE {prefix}account_holds SET seen=? WHERE account_id=? AND worker=? AND seen>?',
                   (time.time(), account, worker, time.time() - HOLD_TTL))
    state = account_state(db, account, prefix)
    return {'held': state['held'], 'owned': state['held'] and state['worker'] == worker}


def account_takeover(db, account, worker, active, prefix='directory.'):
    state = account_state(db, account, prefix)
    if state['held'] and state['worker'] != worker:
        raise ValueError('另一执行窗口正在人工接管，请在该窗口结束接管')
    db.execute(f'UPDATE {prefix}accounts SET held=? WHERE id=?', (int(active), account))
    if active:
        db.execute(f'INSERT OR REPLACE INTO {prefix}account_holds VALUES (?,?,?)', (account, worker, time.time()))
    else:
        db.execute(f'DELETE FROM {prefix}account_holds WHERE account_id=?', (account,))


def legacy_holds(db):
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')
    valid = []
    for row in db.execute("SELECT id,data,created FROM objects WHERE kind='web_hold'").fetchall():
        data = json.loads(row['data'])
        seen = data.get('seen')
        if seen is None:
            worker = db.execute('SELECT seen FROM workers WHERE id=?', (data['worker'],)).fetchone()
            seen = max(datetime.fromisoformat(row['created']).timestamp(), worker[0] if worker else 0)
        if data.get('active') and seen > time.time() - HOLD_TTL:
            valid.append((row['id'], data))
        else:
            db.execute('DELETE FROM objects WHERE id=?', (row['id'],))
    return valid


def scope_account(store, db):
    return db.execute('SELECT account FROM directory.businesses WHERE id=?', (store.scope['business_id'],)).fetchone()[0]


def heartbeat(store, db, worker, takeover=None):
    if store.workspace:
        return account_heartbeat(db, scope_account(store, db), worker, takeover)
    holds = legacy_holds(db)
    for identity, data in holds:
        if data['worker'] == worker and takeover is not False:
            db.execute('UPDATE objects SET data=? WHERE id=?', (json.dumps({**data, 'seen': time.time()}), identity))
    return {'held': bool(holds), 'owned': any(data['worker'] == worker for _, data in holds)}


def state(store, db, worker):
    if store.workspace:
        current = account_state(db, scope_account(store, db))
        return {'held': current['held'], 'owned': current['held'] and current['worker'] == worker}
    holds = legacy_holds(db)
    return {'held': bool(holds), 'owned': any(data['worker'] == worker for _, data in holds)}


def reason_for_account(db, account, prefix='directory.'):
    current = account_state(db, account, prefix)
    if current['conflict']:
        return '账号与已有账号重复，请先处理账号关联'
    return '网页正在人工接管，自动网页操作已暂停' if current['held'] else ''


def block_reason(db):
    if any(row[1] == 'directory' for row in db.execute('PRAGMA database_list')):
        account = db.execute('SELECT b.account FROM directory.businesses b JOIN main.ownership o ON o.business_id=b.id').fetchone()
        return reason_for_account(db, account[0]) if account else ''
    return '网页正在人工接管，自动网页操作已暂停' if legacy_holds(db) else ''


def validate_intent(value):
    if value is not None and type(value) is not bool:
        raise ValueError('接管心跳必须是布尔值')
    return value
