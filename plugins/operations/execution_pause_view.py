"""Show current login observations separately from the durable manual-resume interlock."""
import json

from .execution_pause import account_key, block

AUTH_CODES = {'AUTH_REQUIRED', 'VERIFICATION_REQUIRED'}


def describe(store, reason, db=None):
    if not reason or reason.get('error_code') not in AUTH_CODES:
        return dict(reason or {})
    if db is None:
        with store.connection() as connection:
            return describe(store, reason, connection)
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
        return dict(reason)
    view = {**reason, 'login_state': observed['state'], 'login_checked_at': observed['checked']}
    if observed['state'] == 'unknown':
        view.update(historical_error=reason['error'], error='当前页面登录状态尚待确认；本批次保留此前暂停，请核对账号后手动继续')
        return view
    same_account = bool(observed.get('account_id')) and (not expected or expected == observed['account_id'])
    after_failure = observed['checked'] >= cause_at
    if observed['state'] == 'logged_in' and same_account and after_failure:
        prefix = '已确认登录' if reason.get('cause_at') else '最近已确认登录'
        view.update(historical_error=reason['error'], error=prefix + '；本批次保留此前的暂停状态，请核对账号后手动继续')
    return view
