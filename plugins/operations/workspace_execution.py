"""Shared reservations across isolated topic ledgers, using an attached directory DB."""
import json
import time
import uuid
from datetime import datetime, date
from zoneinfo import ZoneInfo


def check_running(store, *, web=False, db=None):
    if not store.workspace:
        return
    if store.workspace.blocked(store.scope):
        raise ValueError('当前业务、主题或全部运营已暂停/归档')
    if web:
        from .web_control import reason_for_account
        account = store.workspace.resolve(store.scope['business_id'], store.scope['id'])['account']
        if db is None:
            with store.workspace.connection() as connection:
                reason = reason_for_account(connection, account, prefix='')
        else:
            reason = reason_for_account(db, account)
        if reason:
            raise ValueError(reason)


def charge(store, db, day, kind, *, identity=None, account=''):
    if not store.workspace:
        return
    check_running(store)
    limits = json.loads(db.execute("SELECT data FROM directory.preferences WHERE id='limits'").fetchone()[0])
    timezone = ZoneInfo(store.policy()[1]['timezone'])
    at = getattr(store, 'execution_now', None) or datetime.combine(date.fromisoformat(day), datetime.now(timezone).time(), timezone)
    day = at.astimezone(ZoneInfo(limits.get('_timezone', 'Asia/Shanghai'))).date().isoformat()
    used = db.execute('SELECT COALESCE(sum(amount),0) FROM directory.charges WHERE day=? AND kind=? AND account_id=?', (day, kind, account)).fetchone()[0]
    identity = identity or uuid.uuid4().hex
    if db.execute('SELECT 1 FROM directory.charges WHERE id=?', (identity,)).fetchone():
        return
    token_budget = kind == 'model' and limits.get('model_budget_mode') == 'tokens'
    if not token_budget and used >= limits[kind]:
        raise ValueError('达到账号共享额度' if account else '达到 Profile 每日总额度')
    db.execute('INSERT INTO directory.charges VALUES (?,?,?,?,?,?)', (identity, day, kind, 1, store.scope['id'], account))


def reserve_action(store, db, action, identity, day):
    if not store.workspace:
        return True
    sync_actions(store, db)
    check_running(store, web=True, db=db)
    account = store.workspace.resolve(store.scope['business_id'], store.scope['id'])['account']
    registered = db.execute('SELECT identity FROM directory.accounts WHERE id=?', (account,)).fetchone()[0]
    if registered and registered != action['account_id']:
        raise ValueError('实际登录账号与业务关联账号不匹配')
    # A manual rerun is allowed in its owning topic, but cannot duplicate another
    # topic's reply to the same received message or follow candidate.
    row = db.execute('SELECT topic_id FROM directory.account_claims WHERE account_id=? AND kind=? AND target=?', (account, action['kind'], action['target'])).fetchone()
    if row and row[0] != store.scope['id']:
        return False
    if db.execute("SELECT 1 FROM directory.account_actions WHERE account_id=? AND kind=? AND state IN ('queued','executing','submitted','unknown') AND NOT (topic_id=? AND action_id=?)", (account, action['kind'], store.scope['id'], identity)).fetchone():
        raise ValueError('共用账号仍有未完成或待核对动作，请先核对')
    db.execute('INSERT OR IGNORE INTO directory.account_claims VALUES (?,?,?,?,?)', (account, action['kind'], action['target'], store.scope['id'], identity))
    charge(store, db, day, action['kind'], identity=store.scope['id'] + ':' + identity, account=account)
    db.execute("INSERT OR IGNORE INTO directory.account_actions VALUES (?,?,?,?,'queued')", (account, store.scope['id'], identity, action['kind']))
    return True


def claim_account(store, db, command, worker):
    if not store.workspace:
        return True
    check_running(store, web=True, db=db)
    account = store.workspace.resolve(store.scope['business_id'], store.scope['id'])['account']
    row = db.execute('SELECT * FROM directory.account_leases WHERE account_id=?', (account,)).fetchone()
    if row and row['expires'] > time.time():
        return False
    db.execute('INSERT OR REPLACE INTO directory.account_leases VALUES (?,?,?,?,?)', (account, store.scope['id'], worker, command['id'], command['expires']))
    return True


def release_account(store, db, command, worker):
    if store.workspace:
        db.execute('DELETE FROM directory.account_leases WHERE topic_id=? AND command_id=? AND worker=?', (store.scope['id'], command, worker))


def sync_actions(store, db):
    if store.workspace:
        db.execute('UPDATE directory.account_actions SET state=(SELECT state FROM main.actions WHERE id=action_id) WHERE topic_id=? AND action_id IN (SELECT id FROM main.actions)', (store.scope['id'],))


def link_account(directory, business, account):
    from .workspaces import Workspaces
    assert isinstance(directory, Workspaces)
    catalog = directory.catalog()
    if account not in {a['id'] for a in catalog['accounts']}:
        raise ValueError('账号不属于当前 Profile')
    if any(a['id'] == account and a['conflict'] for a in catalog['accounts']):
        raise ValueError('请关联原有账号，或先处理重复登录提示')
    stores = [directory.store(business, topic['id']) for topic in catalog['topics'] if topic['business_id'] == business]
    with directory.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        for store in stores:
            with store.connection() as topic_db:
                if topic_db.execute("SELECT 1 FROM actions WHERE state IN ('queued','executing','submitted','unknown')").fetchone():
                    raise ValueError('请先处理当前账号的未完成动作')
        old = db.execute('SELECT account FROM businesses WHERE id=?', (business,)).fetchone()
        if old and db.execute('SELECT 1 FROM account_leases WHERE account_id=? AND expires>?', (old[0], time.time())).fetchone():
            raise ValueError('当前网页仍在执行任务，请完成后再关联账号')
        if not db.execute('UPDATE businesses SET account=? WHERE id=?', (account, business)).rowcount:
            raise ValueError('业务不存在')


def observe_account(store, body):
    if not store.workspace:
        return
    with store.workspace.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        account = db.execute('SELECT account FROM businesses WHERE id=?', (store.scope['business_id'],)).fetchone()[0]
        record = json.dumps({**body, 'checked': time.time()})
        previous = db.execute('SELECT evidence FROM account_logins WHERE account_id=? AND platform=?', (account, body['platform'])).fetchone()
        evidence = record if body['state'] in {'logged_in', 'logged_out'} else previous[0] if previous else None
        db.execute('INSERT OR REPLACE INTO account_logins VALUES (?,?,?,?)', (account, body['platform'], record, evidence))
        if body['platform'] != 'xiaohongshu' or body['state'] != 'logged_in' or not body.get('account_id'):
            return
        registered = db.execute('SELECT identity FROM accounts WHERE id=?', (account,)).fetchone()[0]
        if registered and registered != body['account_id']:
            db.execute('UPDATE accounts SET conflict=? WHERE id=?', ('changed:' + body['account_id'], account))
            return
        duplicate = db.execute('SELECT id FROM accounts WHERE identity=? AND id!=? AND conflict=\'\'', (body['account_id'], account)).fetchone()
        db.execute('UPDATE accounts SET identity=?,conflict=? WHERE id=?', (body['account_id'], duplicate[0] if duplicate else '', account))
