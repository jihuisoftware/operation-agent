"""Schedule bounded read-only recovery on the existing queue; never resubmit an action."""
import json
from datetime import datetime, UTC
from .review_queue import queue


def reconcile_pending(store, policy, day, now=None):
    now = now or datetime.now(UTC)
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        store._expire(db)
        version = db.execute('SELECT version FROM settings WHERE id=1').fetchone()[0]
        pending = db.execute("SELECT * FROM actions WHERE state IN ('unknown','submitted') ORDER BY created").fetchall()
        queued = 0
        for row in pending:
            action = json.loads(row['data'])
            if policy['account_id'] and action['account_id'] != policy['account_id']:
                continue
            if queue(db, row, version, now=now):
                queued += 1
            if queued >= 5:
                break
