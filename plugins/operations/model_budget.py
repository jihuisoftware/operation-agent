"""A diagnostic batch allowance can only narrow the standing daily allowance."""
import json

from .run_scope import belongs, runs_for_batch


def remaining_calls(store, policy, day, db=None):
    if db is None:
        with store.connection() as connection:
            return remaining_calls(store, policy, day, connection)
    rows = [json.loads(row[0]) for row in db.execute(
        "SELECT data FROM events WHERE kind='model_call' AND json_extract(data,'$.day')=?", (day,))]
    remaining = max(0, policy['model_calls'] - len(rows))
    allowance = (store.run_options or {}).get('model_calls')
    if type(allowance) is not int or allowance < 0:
        return remaining
    batch = store.manual_run_id
    if batch:
        ids = {row['id'] for row in runs_for_batch(db, day, batch)}
        used = sum(belongs(row, batch, ids) for row in rows)
    else:
        used = sum(row.get('run_id') == store.current_run_id for row in rows)
    return max(0, min(remaining, allowance - used))
