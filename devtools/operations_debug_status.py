"""Small per-task projections for the debug list; full events stay in the detail endpoint."""
from datetime import UTC, datetime
from copy import deepcopy
import json


def persist_recovery(store, data, original):
    from plugins.operations.store import encoded
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT data FROM objects WHERE id=? AND kind='debug_run'", (data['id'],)).fetchone()
        if row and json.loads(row[0]) == json.loads(original):
            db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(data), data['id']))
        elif row:
            data.clear()
            data.update(json.loads(row[0]))


def present_run(store, run):
    if run.get('state') != 'paused':
        return run
    from plugins.operations.execution_pause import load
    from plugins.operations.execution_pause_view import describe
    reason = load(store, run['id'])
    if not reason:
        return run
    view = describe(store, reason)
    presented = deepcopy(run)
    presented['pause_status'] = view
    if view.get('historical_error'):
        presented['detail'] = view['error']
        for step in presented.get('steps', []):
            if step['state'] == 'paused':
                step['historical_detail'] = step.get('detail', '')
                step['detail'] = view['error']
    return presented


def latest_progress(store, identities):
    if not identities:
        return {}
    placeholders = ','.join('?' for _ in identities)
    with store.connection() as db:
        rows = db.execute(f"SELECT at,json_extract(data,'$.debug_id') AS batch,json_extract(data,'$.step_id') AS step,"
                          f"json_extract(data,'$.detail') AS detail FROM events WHERE id IN (SELECT max(id) FROM events "
                          f"WHERE kind='progress' AND json_extract(data,'$.debug_id') IN ({placeholders}) "
                          "GROUP BY json_extract(data,'$.debug_id'),json_extract(data,'$.step_id'))", identities).fetchall()
    result = {}
    for row in rows:
        result[(row['batch'], row['step'])] = {'detail': str(row['detail'] or '')[:500], 'progress_at': row['at']}
    return result


def task_status(store, runs):
    progress = latest_progress(store, [run['id'] for run in runs if run['state'] == 'running'])
    result = {}
    for run in runs:
        pipeline = run['task'] == 'pipeline'
        steps = run.get('steps', []) if pipeline else [{**run, 'id': run['task']}]
        for step in steps:
            identity = step['id']
            if identity in result:
                continue
            row = {key: step[key] for key in ('state', 'started', 'ended', 'duration_ms') if key in step}
            row.update(run_id=run['id'], mode=run.get('mode', 'normal'), detail=str(step.get('detail', ''))[:500])
            row.update(saved_result_status(run, step))
            if row['state'] == 'running':
                row.update(progress.get((run['id'], identity if pipeline else None), {}))
                started = row.get('started', run['started'])
                row['duration_ms'] = max(0, int((datetime.now(UTC) - datetime.fromisoformat(started)).total_seconds() * 1000))
            result[identity] = row
    return result


def saved_result_status(run, step):
    saved = step.get('result')
    if step['id'] == 'content' and isinstance(saved, dict) and saved.get('content_id') and step['state'] in {'completed', 'needs_attention'}:
        from plugins.operations.outcomes import describe
        state, detail = describe('content', saved)
        return {'state': state, 'detail': detail[:500]}
    # Correct the old generic dependency label without changing the stored execution log.
    if step['id'] == 'publish' and step['state'] == 'skipped' and str(step.get('detail', '')).startswith('依赖步骤「内容生产」未完成'):
        from .operations_pipeline import dependency_reason
        reason = dependency_reason(run, 'publish')
        if reason.startswith('本轮草稿已生成'):
            return {'detail': reason[:500]}
    return {}


def active_execution(store):
    import time
    from plugins.operations.batch_cancellation import recover_lease
    recover_lease(store)
    from plugins.operations.manual import LABELS
    with store.connection() as db:
        lease = db.execute("SELECT token FROM leases WHERE id='account' AND expires>?", (time.time(),)).fetchone()
        if not lease:
            return None
        from plugins.operations.batch_cancellation import requested
        if requested(db, lease['token']):
            return {'message': '已请求取消，正在等待在途调用结束；不会执行后续步骤'}
        row = db.execute("SELECT id,stage,started FROM runs WHERE state='running' ORDER BY started DESC LIMIT 1").fetchone()
        if not row:
            return {'message': '已有任务占用执行通道，请等待当前任务结束'}
        progress = db.execute("SELECT at,json_extract(data,'$.detail') AS detail FROM events WHERE kind='progress' "
                              "AND json_extract(data,'$.run_id')=? ORDER BY id DESC LIMIT 1", (row['id'],)).fetchone()
    detail = str(progress['detail'] or '')[:500] if progress else '任务执行中'
    return {'run_id': row['id'], 'started': row['started'], 'progress_at': progress['at'] if progress else None,
            'message': f"后台正在执行「{LABELS.get(row['stage'], row['stage'])}」：{detail}"}
