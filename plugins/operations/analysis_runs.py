"""Single-stage manual execution shares the same lease, runs and progress journal."""
import json
import re

from .policy import local_day, now_iso
from .outcomes import StageSkipped


class AnalysisCancelled(StageSkipped):
    pass


def guard(store, policy):
    store.renew()
    if store.policy()[1] != policy or not policy['enabled'] or policy['paused']:
        raise AnalysisCancelled('分析已暂停或规则发生变化')
    if store.current_run_id:
        with store.connection() as db:
            found = db.execute("SELECT 1 FROM objects WHERE id=?", ('analysis-cancel:' + store.current_run_id,)).fetchone()
        if found:
            raise AnalysisCancelled('人工取消分析；已产生的历史结果保留')


def run(store, stage, body):
    from .runtime import _execute
    if stage not in ('analytics', 'industry') or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', str(body.get('request_id', ''))):
        raise ValueError('任务或请求 ID 无效')
    version, policy = store.policy()
    if body.get('version') != version or not policy['enabled'] or policy['paused'] or not policy['modules'][stage]:
        raise ValueError('请启用对应分析模块并刷新规则')
    slot = 'analysis:' + body['request_id']
    with store.connection() as db:
        prior = db.execute('SELECT * FROM runs WHERE slot=?', (slot,)).fetchone()
    if prior:
        if prior['stage'] != stage or prior['version'] != version:
            raise ValueError('同一请求不能用于不同任务或规则')
        return dict(prior)
    if not store.lease(slot):
        raise ValueError('已有运营任务执行中，请稍后再试')
    try:
        day = local_day(policy)
        identity = store.start_run(day, stage, slot, version)
        _execute(store, policy, day, version, stage, identity)
        with store.connection() as db:
            return dict(db.execute('SELECT * FROM runs WHERE id=?', (identity,)).fetchone())
    finally:
        store.release(slot)


def cancel(store, identity):
    with store.connection() as db:
        row = db.execute('SELECT * FROM runs WHERE id=?', (identity,)).fetchone()
    if not row or row['stage'] not in ('analytics', 'industry') or row['state'] != 'running':
        raise ValueError('没有可取消的正在执行分析')
    store.put('analysis_cancel', {'run_id': identity, 'created': now_iso()}, 'analysis-cancel:' + identity)
    return {'ok': True, 'detail': '已请求取消，当前模型调用返回后停止，不再发起后续调用'}


def logs(store, identity):
    with store.connection() as db:
        run = db.execute("SELECT * FROM runs WHERE id=? AND stage IN ('analytics','industry')", (identity,)).fetchone()
        if not run:
            raise ValueError('分析运行不存在')
        events = [{**dict(e), 'data': json.loads(e['data'])} for e in db.execute(
            "SELECT * FROM events WHERE json_extract(data,'$.run_id')=? ORDER BY id", (identity,))]
    return {'run': dict(run), 'events': events, 'errors': [e for e in events if e['data'].get('state') in ('failed', 'cancelled') or e['data'].get('error')]}
