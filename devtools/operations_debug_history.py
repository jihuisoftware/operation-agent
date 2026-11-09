"""Clear the debug history view without deleting business or recovery evidence."""
from fastapi import APIRouter

from plugins.operations.policy import now_iso
from plugins.operations.store import Store

router = APIRouter()
FINISHED = ('completed', 'failed', 'skipped', 'interrupted', 'needs_attention', 'cancelled')


def clear_history(store):
    placeholders = ','.join('?' for _ in FINISHED)
    stamp = now_iso()
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        count = db.execute(
            "INSERT OR IGNORE INTO objects(id,kind,data,created) SELECT 'debug-history-hidden:'||r.id,'debug_history_hidden',"
            "json_object('debug_id',r.id,'cleared_at',?),? FROM objects r WHERE r.kind='debug_run' "
            f"AND json_extract(r.data,'$.state') IN ({placeholders}) AND NOT EXISTS(SELECT 1 FROM objects p "
            "WHERE p.id='execution-pause:'||r.id AND p.kind='execution_pause' AND json_extract(p.data,'$.state')='paused')",
            (stamp, stamp, *FINISHED)).rowcount
        retained = db.execute("SELECT count(*) FROM objects r WHERE r.kind='debug_run' AND NOT EXISTS(SELECT 1 FROM objects h "
                              "WHERE h.id='debug-history-hidden:'||r.id AND h.kind='debug_history_hidden')").fetchone()[0]
    return {'cleared': count, 'retained': retained}


@router.post('/history/clear')
def clear():
    from .operations_debug import require_enabled
    require_enabled()
    return clear_history(Store())
