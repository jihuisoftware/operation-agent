"""One Profile schedule, independent of any particular business or topic."""
import json
from .policy import now_iso


def schedule_id(store, db=None):
    if db is None:
        with (store.workspace.connection() if store.workspace else store.connection()) as connection:
            return schedule_id(store, connection)
    query = "SELECT data FROM preferences WHERE id='schedule'" if store.workspace else "SELECT data FROM objects WHERE kind='schedule' ORDER BY created DESC LIMIT 1"
    row = db.execute(query).fetchone()
    return json.loads(row[0])['job_id'] if row else None


def save_schedule(store, db, identity):
    data = json.dumps({'job_id': identity})
    if store.workspace:
        db.execute("INSERT OR REPLACE INTO preferences VALUES ('schedule',?)", (data,))
    else:
        db.execute("INSERT OR REPLACE INTO objects VALUES ('schedule','schedule',?,?)", (data, now_iso()))
