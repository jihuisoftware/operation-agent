"""Timeouts distinguish unread commands, read-only work and uncertain submissions."""
import json
import time

from .execution_pause import CODES, pause
from .store import encoded


def dispatch_state(db, command):
    if command['worker'] is None:
        return 'not_started'
    if command['kind'] not in {'publish', 'interact'}:
        return 'read_only'
    # A claimed write without a terminal receipt is not proof of non-submission.
    # Older workers may have no trace; only an explicit fenced receipt can narrow it.
    return 'submission_started'


def expire(store, db):
    from .workspace_execution import release_account
    rows = db.execute("SELECT * FROM commands WHERE kind!='verify' AND state IN ('queued','running') AND expires<?", (time.time(),)).fetchall()
    for command in rows:
        phase = dispatch_state(db, command)
        uncertain = phase == 'submission_started'
        result = {'state': 'unknown' if uncertain else 'blocked', 'error_code': 'COMMAND_EXPIRED',
                  'dispatch_state': phase, 'interruption_scope': 'batch', 'submitted': uncertain,
                  'error': {'not_started': '桌面未接收任务，尚未执行；请恢复执行窗口后手动继续',
                            'read_only': '网页读取中断，尚未提交；请检查页面后手动继续',
                            'submission_started': '提交已开始但未收到结果，请核对后再继续'}[phase]}
        db.execute('UPDATE commands SET state=?,result=? WHERE id=?', ('unknown' if uncertain else 'interrupted', encoded(result), command['id']))
        if command['action_id']:
            db.execute('UPDATE actions SET state=?,result=? WHERE id=?', ('unknown' if uncertain else 'blocked', encoded(result), command['action_id']))
        release_account(store, db, command['id'], command['worker'])
        result['cause_command_id'] = command['id']
        if not json.loads(command['payload']).get('wake_probe'):
            pause(store, result, db=db, payload=json.loads(command['payload']))


def receipt(store, db, command, result):
    if result.get('error_code') in CODES:
        result['cause_command_id'] = command['id']
        if not json.loads(command['payload']).get('wake_probe'):
            pause(store, result, db=db, payload=json.loads(command['payload']))


def late(db, identity, worker, result):
    row = db.execute("SELECT * FROM commands WHERE id=? AND worker=? AND state IN ('interrupted','unknown')", (identity, worker)).fetchone()
    if not row or result.get('error_code') not in CODES:
        return None
    sleep_unknown = result.get('error_code') == 'SYSTEM_SUSPENDED' and result.get('dispatch_state') == 'submission_started' and result.get('submitted') is True
    if not sleep_unknown and (result.get('dispatch_state') not in {'read_only', 'not_started'} or result.get('submitted') is not False):
        return None
    if row['action_id']:
        action = db.execute('SELECT state,result FROM actions WHERE id=?', (row['action_id'],)).fetchone()
        newer = db.execute('SELECT id FROM commands WHERE action_id=? ORDER BY rowid DESC LIMIT 1', (row['action_id'],)).fetchone()
        if action['state'] not in {'blocked', 'unknown'} or json.loads(action['result']).get('manual_verification') or newer[0] != identity:
            return None
    result['late_receipt'] = True
    return row
