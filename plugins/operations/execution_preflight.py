"""An explicit new start can recheck an old login latch, without resuming historical batches."""
import time

from .execution_pause import ExecutionPaused, account_key, block, clear_block, propagate
from .policy import local_day

AUTH_CODES = {'AUTH_REQUIRED', 'VERIFICATION_REQUIRED'}


def recoverable(reason):
    # A fresh account probe restores the executor, never the old submission.
    # Original uncertain actions remain fenced by manuscript/batch admission.
    return reason.get('error_code') in AUTH_CODES | {'BROWSER_UNAVAILABLE', 'COMMAND_EXPIRED', 'SYSTEM_SUSPENDED'}


def _snapshot(store, version, db):
    current, policy = store.policy()
    if current != version or not policy['enabled'] or policy['paused']:
        raise ValueError('启动前规则已变化或计划已暂停，请刷新后重新发起')
    from .workspace_execution import check_running
    check_running(store, db=db)
    from .readiness import web_block_reason
    held = web_block_reason(db)
    if held:
        raise ExecutionPaused({'error_code': 'CONTROL_PAUSED', 'error': held + '；请结束接管后重新发起', 'interruption_scope': 'batch'})
    account = account_key(store, db)
    expected = policy['account_id']
    if store.workspace and not expected:
        expected = db.execute('SELECT identity FROM directory.accounts WHERE id=?', (account,)).fetchone()[0]
    return {'version': version, 'day': local_day(policy), 'account_link': account, 'account_id': expected}


def verify_for_start(store, version):
    from .execution_pause import identity, load
    current = load(store, identity(store))
    if current and current['state'] == 'paused':
        raise ExecutionPaused(current)
    old = block(store)
    if not old or not recoverable(old):
        return None
    try:
        return _verify(store, version, old)
    except ExecutionPaused as exc:
        propagate(store, exc.result)
        store.event('account_preflight', {'state': 'paused', 'error': str(exc), 'error_code': exc.result['error_code']})
        raise
    except ValueError as exc:
        reason = {'error_code': 'REVALIDATION_REQUIRED', 'error': str(exc), 'interruption_scope': 'batch'}
        propagate(store, reason)
        store.event('account_preflight', {'state': 'paused', **reason})
        raise ExecutionPaused(reason) from exc


def _verify(store, version, old):
    with store.connection() as db:
        expected = _snapshot(store, version, db)
    receipt = {'block_before': old, 'started': time.time()}
    from .workflow import browser
    observed = browser(store, 'account', {'resume_probe': True, 'preflight': 'explicit_start'})
    if observed.get('state') != 'logged_in' or not observed.get('account_id'):
        raise ExecutionPaused({'error_code': 'BROWSER_UNAVAILABLE', 'error': '启动前尚未确认实际登录账号，请检查页面后重试', 'interruption_scope': 'batch'})
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        current = _snapshot(store, version, db)
        if current != expected or (expected['account_id'] and observed['account_id'] != expected['account_id']):
            raise ValueError('登录检查期间账号、日期或规则已变化，请核对后重新发起')
        from .execution_resume import _check_probe
        _check_probe(store, db, receipt, observed)
        clear_block(store, db)
    result = {'state': 'logged_in', 'account_id': observed['account_id'], 'cleared_error_code': old['error_code'],
              'detail': '启动前已核对执行窗口和实际账号，允许本次所选执行；历史批次未自动恢复'}
    store.event('account_preflight', {**result, 'day': expected['day']})
    return result
