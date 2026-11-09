"""Snapshot current pause observations and selected, unstarted steps for one report scope."""
from datetime import datetime, UTC
import json

from .execution_pause_view import describe
from .manual import LABELS


def _pauses(scope, db):
    rows = [json.loads(row[0]) for row in db.execute(
        "SELECT data FROM objects WHERE kind='execution_pause' AND json_extract(data,'$.day')=?", (scope.day,))]
    if scope.batch:
        key = scope.batch if scope.batch.startswith(('debug:', 'manual:', 'quick:')) else 'manual:' + scope.batch
        return [row for row in rows if row['id'] == key]
    return rows


def _selected(scope, db):
    if not scope.batch or not scope.batch.startswith('debug:'):
        return []
    row = db.execute("SELECT data FROM objects WHERE kind='debug_run' AND id=?", (scope.batch,)).fetchone()
    data = json.loads(row[0]) if row else {}
    if data.get('day') != scope.day:
        return []
    steps = data.get('steps', [])
    selection = data.get('selected_tasks')
    selected = set([step['id'] for step in steps] if selection is None else selection)
    return [step for step in steps if step['id'] in selected and step['id'] != 'report']


def snapshot(scope):
    with scope.store.connection() as db:
        pauses = _pauses(scope, db)
        steps = _selected(scope, db)
        views = {row['id']: describe(scope.store, row, db) for row in pauses}
    by_run = {step.get('run_id'): step for step in steps if step.get('run_id')}
    represented = set()
    runs = []
    for row in scope.runs:
        step = by_run.get(row['id']) or _step_for_slot(scope.batch, row, steps)
        if step:
            represented.add(step['id'])
        item = {**row, 'title': step.get('title', LABELS.get(row['stage'], row['stage']))}
        reason = next((pause for pause in pauses if scope.batch or row['id'] in {pause['id'], pause.get('run_id')}
                       or row['slot'] == pause.get('slot')), None)
        if row['state'] == 'paused' and reason:
            item['historical_detail'] = row['detail']
            item['detail'] = views[reason['id']]['error']
            item['historical_pause'] = reason['state'] != 'paused'
        runs.append(item)
    seen = {row['id'] for row in scope.runs}
    reason = next((views[row['id']] for row in pauses if row['state'] == 'paused'), None)
    for step in steps:
        if step['state'] != 'paused' or step.get('run_id') in seen or step['id'] in represented:
            continue
        detail = reason['error'] if reason else step.get('detail', '本批次已暂停')
        runs.append({'id': scope.batch + ':unstarted:' + step['id'], 'stage': step.get('module', step['id']),
                     'title': step.get('title', LABELS.get(step['id'], step['id'])), 'state': 'paused',
                     'detail': detail + '；尚未开始，等待本批次手动继续', 'historical_detail': step.get('detail', ''),
                     'unstarted': True})
    return {'runs': runs, 'pause_observations': list(views.values())}


def _step_for_slot(batch, row, steps):
    if not batch:
        return {}
    for step in steps:
        slot = batch + ':' + step['id']
        if row['slot'] == slot or row['slot'].startswith(slot + ':resume:'):
            return step
    return {}


def observation_lines(execution):
    observations = execution['pause_observations']
    if not observations:
        return []
    lines = ['', '## 暂停依据与登录观察', '', '以下记录为生成日报时的观察快照；历史原因不代表账号当前仍处于同一状态。']
    for item in observations:
        lines.extend([f"- 暂停记录：{item['id']}", f"  历史暂停原因：{item.get('historical_error', item['error'])}",
                      f"  暂停时间：{item.get('paused_at', '未记录')}", f"  当前说明：{item['error']}"])
        if item.get('cause_run_id'):
            lines.append(f"  原始任务：{item['cause_run_id']}（{item.get('cause_stage', '网页任务')}）")
        if item.get('cause_at'):
            cause = datetime.fromtimestamp(item['cause_at'], UTC).isoformat()
            lines.append(f'  原始失效观察时间：{cause}')
        if item.get('login_checked_at') is not None:
            checked = datetime.fromtimestamp(item['login_checked_at'], UTC).isoformat()
            lines.extend([f"  登录观察状态：{item['login_state']}", f'  登录观察时间：{checked}'])
        else:
            lines.append('  登录观察时间：尚无可用观察记录')
    return lines


def preflight_lines(scope):
    event = next((row for row in reversed(scope.events) if row['kind'] == 'account_preflight'), None)
    if not event:
        return []
    data = json.loads(event['data'])
    if data.get('state') == 'logged_in':
        detail = '核对通过：启动前已确认实际登录。此结果仅说明账号核对通过，外部动作结果以下方记录为准。'
        if data.get('cleared_error_code') in {'AUTH_REQUIRED', 'VERIFICATION_REQUIRED'}:
            detail += '旧登录暂停已解除；历史批次未自动恢复。'
    else:
        reasons = {'AUTH_REQUIRED': '当前页面需要重新登录', 'VERIFICATION_REQUIRED': '当前页面需要安全验证',
                   'ACCOUNT_CHANGED': '当前账号与本次任务要求不一致', 'BROWSER_UNAVAILABLE': '暂时无法确认实际登录',
                   'REVALIDATION_REQUIRED': '账号、日期或规则变化，需要重新核对', 'RESULT_UNCERTAIN': '仍有待核对的外部动作',
                   'CONTROL_PAUSED': '网页控制尚未释放', 'COMMAND_EXPIRED': '账号核对未能按时完成'}
        reason = reasons.get(data.get('error_code'), '尚未确认账号可用于本次任务')
        detail = f'核对未通过：{reason}。请处理阻塞后重新发起；本项不代表外部动作已执行。'
    return ['', '## 启动前账号核对', '', detail, f"核对时间：{event['at']}", '']
