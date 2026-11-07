"""Show current login observations separately from the durable manual-resume interlock."""
import json

from .execution_pause import account_key, block

AUTH_CODES = {'AUTH_REQUIRED', 'VERIFICATION_REQUIRED'}


def describe(store, reason, db=None):
    if not reason:
        return {}
    if db is None:
        with store.connection() as connection:
            return describe(store, reason, connection)
    from .pause_origin import legacy_view
    view = legacy_view(db, reason)
    if view.get('inherited'):
        from .manual import LABELS
        stage = LABELS.get(view.get('cause_step'), LABELS.get(view.get('cause_stage'), '网页任务'))
        at = view.get('cause_started_at') or view.get('at') or ''
        view.update(historical_error=reason['error'],
                    error=f"受此前{stage}的阻塞影响，本次尚未执行；原始原因：{reason['error']}", cause_started_at=at)
    if reason.get('error_code') not in AUTH_CODES:
        return _wake_view(store, view, db)
    policy = json.loads(db.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
    expected = reason.get('account_id') or policy['account_id']
    current = block(store, db) or {}
    cause_at = max(reason.get('cause_at', 0), current.get('cause_at', 0))
    if store.workspace:
        account = account_key(store, db)
        row = db.execute("SELECT record FROM directory.account_logins WHERE account_id=? AND platform='xiaohongshu'", (account,)).fetchone()
        observed = json.loads(row[0]) if row else None
        registered = db.execute('SELECT identity FROM directory.accounts WHERE id=?', (account,)).fetchone()
        expected = expected or (registered[0] if registered else '')
    else:
        row = db.execute("SELECT * FROM platform_logins WHERE platform='xiaohongshu' ORDER BY checked DESC,rowid DESC LIMIT 1").fetchone()
        observed = dict(row) if row else None
    if not observed:
        return view
    view.update(login_state=observed['state'], login_checked_at=observed['checked'])
    if observed['state'] == 'unknown':
        view.update(historical_error=reason['error'], error='当前页面登录状态尚待确认；本批次保留此前暂停，请核对账号后手动继续')
        return view
    same_account = bool(observed.get('account_id')) and (not expected or expected == observed['account_id'])
    after_failure = observed['checked'] >= cause_at
    if observed['state'] == 'logged_in' and same_account and after_failure:
        prefix = '已确认登录' if reason.get('cause_at') else '最近已确认登录'
        view.update(historical_error=reason['error'], error=prefix + '；本批次保留此前的暂停状态，请核对账号后手动继续')
    return view


def _wake_view(store, view, db):
    if not store.workspace:
        return view
    account = account_key(store, db)
    row = db.execute("SELECT data FROM directory.preferences WHERE id=?", ('wake-status:' + account,)).fetchone()
    status = json.loads(row[0]) if row else None
    current = block(store, db) or {}
    if status and status.get('state') == 'ready' and status.get('checked_epoch', 0) >= max(view.get('cause_at', 0), current.get('cause_at', 0)):
        view.update(revalidation=status, historical_error=view.get('historical_error', view['error']),
                    error=view['error'] + '；账号已确认，等待手动继续')
    return view
