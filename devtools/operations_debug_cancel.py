"""Cancel the active debug batches in one authorized workspace snapshot."""
import json
import re

from fastapi import APIRouter, HTTPException
from plugins.operations.batch_cancellation import cancel_commands, mark
from plugins.operations.policy import now_iso
from plugins.operations.store import Store, encoded

router = APIRouter()


def cancel_all(store, request_id):
    if not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', request_id):
        raise ValueError('取消请求标识无效')
    key, stamp = 'debug-cancel-request:' + request_id, now_iso()
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        prior = db.execute('SELECT data FROM objects WHERE id=?', (key,)).fetchone()
        if prior:
            return json.loads(prior[0])
        rows = db.execute("SELECT r.id,r.data FROM objects r WHERE r.kind='debug_run' AND "
                          "(json_extract(r.data,'$.state') IN ('running','pending','paused') OR EXISTS(SELECT 1 FROM objects p "
                          "WHERE p.id='execution-pause:'||r.id AND p.kind='execution_pause' AND json_extract(p.data,'$.state')='paused'))").fetchall()
        batches = {row['id']: json.loads(row['data']) for row in rows}
        starting = db.execute("SELECT token FROM leases WHERE id='account' AND substr(token,1,6)='debug:' AND NOT EXISTS "
                              "(SELECT 1 FROM objects WHERE id=leases.token AND kind='debug_run')").fetchone()
        if starting:
            batches[starting[0]] = None
        queued = 0
        for batch, data in batches.items():
            db.execute("INSERT OR IGNORE INTO objects VALUES (?,'batch_cancel',?,?)", ('batch-cancel:' + batch, encoded({'batch_id': batch, 'at': stamp}), stamp))
            if data:
                db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(mark(data, stamp)), batch))
            queued += cancel_commands(db, batch)
            db.execute("UPDATE runs SET state='cancelled',detail='用户取消本批次',ended=? WHERE state IN ('running','pending','paused') "
                       "AND (slot=? OR substr(slot,1,?)=?)", (stamp, batch, len(batch) + 1, batch + ':'))
            db.execute("UPDATE objects SET data=json_set(data,'$.state','cancelled','$.ended',?) WHERE id=? AND kind='execution_pause'", (stamp, 'execution-pause:' + batch))
            db.execute("UPDATE objects SET data=json_set(data,'$.state','cancelled','$.ended',?) WHERE kind='execution_resume' AND json_extract(data,'$.id')=?", (stamp, batch))
        from plugins.operations.workspace_execution import sync_actions
        sync_actions(store, db)
        result = {'cancelled': len(batches), 'queued_commands_cancelled': queued,
                  'detail': '已停止后续步骤；在途调用结束后释放执行通道，已提交动作仍可核对'}
        db.execute("INSERT INTO objects VALUES (?,'debug_cancel_request',?,?)", (key, encoded(result), stamp))
        return json.loads(db.execute('SELECT data FROM objects WHERE id=?', (key,)).fetchone()[0])


@router.post('/cancel-all')
def cancel(body: dict):
    from .operations_debug import require_enabled
    require_enabled()
    try:
        return cancel_all(Store(), body.get('request_id'))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
