"""Durable debug-batch cancellation; never revoke a submitted action's evidence."""
import json

from .analysis_runs import AnalysisCancelled
from .policy import now_iso
from .store import encoded

MESSAGE = '用户已取消本批次，已完成成果保留；已提交动作仅核对，不重新发送'


class BatchCancelled(AnalysisCancelled):
    def __init__(self):
        super().__init__(MESSAGE)


def requested(db, batch):
    return bool(batch and db.execute("SELECT 1 FROM objects WHERE id=? AND kind='batch_cancel'",
                                    ('batch-cancel:' + batch,)).fetchone())


def check(store, *, db=None, batch=None):
    batch = batch or store.manual_run_id or getattr(store, 'debug_id', None)
    if not batch or not batch.startswith('debug:'):
        return
    if db is None:
        with store.connection() as connection:
            return check(store, db=connection, batch=batch)
    if requested(db, batch):
        raise BatchCancelled()


def payload_cancelled(db, command):
    return command['kind'] != 'verify' and requested(db, json.loads(command['payload']).get('manual_run_id'))


def mark(data, stamp):
    data.update(state='cancelled', detail=MESSAGE, ended=stamp, cancellation_requested_at=stamp)
    for step in data.get('steps', []):
        if step['state'] in {'pending', 'running', 'paused'}:
            step.update(state='cancelled', detail='本步骤已取消，不再执行后续操作', ended=stamp)
    if 'counts' in data:
        data['counts']['cancelled'] = sum(step['state'] == 'cancelled' for step in data.get('steps', []))
    return data


def preserve(db, data):
    if not requested(db, data['id']):
        return
    row = db.execute("SELECT data FROM objects WHERE id=? AND kind='debug_run'", (data['id'],)).fetchone()
    current = json.loads(row[0]) if row else data.copy()
    if current.get('state') != 'cancelled':
        mark(current, now_iso())
    data.clear()
    data.update(current)


def cancel_commands(db, batch):
    commands = db.execute("SELECT id,action_id FROM commands WHERE state='queued' AND kind!='verify' "
                          "AND json_extract(payload,'$.manual_run_id')=?", (batch,)).fetchall()
    result = encoded({'state': 'cancelled', 'error_code': 'BATCH_CANCELLED', 'error': MESSAGE,
                      'submitted': False, 'dispatch_state': 'not_started'})
    for command in commands:
        db.execute("UPDATE commands SET state='cancelled',result=? WHERE id=?", (result, command['id']))
        if command['action_id']:
            db.execute("UPDATE actions SET state='cancelled',result=? WHERE id=? AND state='queued'", (result, command['action_id']))
    return len(commands)


def worker_commands(db, worker):
    return [row[0] for row in db.execute("SELECT c.id FROM commands c WHERE c.worker=? AND c.state='running' AND c.kind!='verify' "
            "AND EXISTS(SELECT 1 FROM objects o WHERE o.id='batch-cancel:'||json_extract(c.payload,'$.manual_run_id') AND o.kind='batch_cancel')", (worker,))]


def receipt(db, command, result):
    if not payload_cancelled(db, command):
        return result
    if result.get('state') in {'published', 'submitted', 'confirmed'}:
        return {**result, 'cancellation_requested': True}
    not_submitted = command['kind'] not in {'publish', 'interact'} or (
        result.get('submitted') is False and result.get('dispatch_state') in {'not_started', 'read_only'})
    return {**result, 'state': 'cancelled' if not_submitted else 'unknown', 'error_code': 'BATCH_CANCELLED',
            'error': MESSAGE, 'submitted': not not_submitted, 'cancellation_requested': True}


def recover_lease(store):
    """A cancelled owner's dead process cannot keep the topic busy after restart."""
    import psutil
    with store.connection() as db:
        row = db.execute("SELECT l.token,r.data FROM leases l JOIN objects r ON r.id=l.token AND r.kind='debug_run' "
                         "WHERE l.id='account' AND EXISTS(SELECT 1 FROM objects c WHERE c.id='batch-cancel:'||l.token AND c.kind='batch_cancel')").fetchone()
    if not row:
        return
    owner = json.loads(row['data'])
    if not owner.get('pid') or owner.get('process_started') is None:
        return
    try:
        if psutil.Process(owner['pid']).create_time() == owner['process_started']:
            return
    except psutil.NoSuchProcess:
        pass
    except psutil.AccessDenied:
        return
    with store.connection() as db:
        db.execute("DELETE FROM leases WHERE id='account' AND token=?", (row['token'],))
