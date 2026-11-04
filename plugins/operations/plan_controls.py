"""Explicit plan controls shared by the simplified UI and existing Cron service."""
from .policy import now_iso
from .store import encoded


def control(store, body):
    version, policy = store.policy()
    if body.get('version') != version:
        raise ValueError('配置已变更，请刷新后再操作')
    action = body.get('action')
    if action in {'pause', 'resume'}:
        policy.update(paused=action == 'pause', enabled=True)
        version = store.configure(policy, version, activation=True)
        from .runtime import ensure_schedule
        ensure_schedule(store)
        return {'version': version}
    if action == 'run':
        from .workspace_execution import check_running
        check_running(store)
        if not policy['enabled'] or policy['paused']:
            raise ValueError('请先启用计划或解除全局暂停')
        from .runtime import ensure_schedule
        from cron.jobs import trigger_job
        if store.workspace:
            import uuid
            from .workspace_runtime import request_run
            request_run(store, body.get('request_id') or uuid.uuid4().hex)
        return {'job_id': trigger_job(ensure_schedule(store))['id']}
    raise ValueError('未知计划操作')


def check_cancelled(store):
    from .execution_pause import guard
    guard(store)
    from .workspace_execution import check_running
    check_running(store)
    if not store.manual_run_id:
        return
    from .collection_ledger import load
    value = load(store, store.manual_run_id)
    if value and value.get('state') == 'cancelled':
        from .analysis_runs import AnalysisCancelled
        raise AnalysisCancelled('已取消快速首轮')


def cancel_first(store, identity):
    from .collection_ledger import load
    value = load(store, identity)
    if not identity.startswith('quick:') or not value:
        raise ValueError('首轮记录不存在')
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        value.update(state='cancelled', detail='用户取消首轮，已提交动作仍须核对', ended=now_iso())
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(value), identity))
        db.execute("UPDATE commands SET state='cancelled' WHERE state='queued' AND json_extract(payload,'$.manual_run_id')=?", (identity,))
        db.execute("UPDATE actions SET state='cancelled' WHERE state='queued' AND json_extract(data,'$.manual_run_id')=?", (identity,))
    return {'state': 'cancelled'}
