"""Manual request steps come from the same durable queue as the dispatcher."""
import json
from .policy import local_day, now_iso


def queue_due(store, policy, now):
    from .occurrences import latest_due
    due = latest_due(store, policy, now)
    if not store.workspace:
        return due
    # One durable latest occurrence per stage; displaced occurrences leave no history.
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM directory.scheduled_queue WHERE topic_id=?', (store.scope['id'],))
        for stage, stamp in due.items():
            if not db.execute('SELECT 1 FROM runs WHERE day=? AND stage=? AND slot=?', (stamp.date().isoformat(), stage, stamp.strftime('%H:%M'))).fetchone():
                db.execute('INSERT INTO directory.scheduled_queue VALUES (?,?,?)', (store.scope['id'], stage, stamp.isoformat()))
    return due


def pending(store):
    from .upcoming import item
    _, policy = store.policy()
    with store.connection() as db:
        requests = db.execute("SELECT id FROM directory.requests WHERE topic_id=? AND state IN ('pending','running') ORDER BY rowid", (store.scope['id'],)).fetchall()
        rows = []
        for request in requests:
            batch = db.execute('SELECT data FROM objects WHERE id=?', ('manual:' + request['id'],)).fetchone()
            day = json.loads(batch[0])['day'] if batch else local_day(policy)
            slot = 'manual:' + request['id']
            done = {r[0]: r[1] for r in db.execute('SELECT stage,state FROM runs WHERE slot=?', (slot,))}
            rows.extend(item(day, stage, slot, now_iso(), done.get(stage, 'pending')) for stage, enabled in policy['modules'].items()
                        if enabled and done.get(stage, 'pending') in {'pending', 'cancelled'})
    return rows
