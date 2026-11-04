"""Reconcile abandoned reservations without treating missing receipts as free usage."""
import json
import os

import psutil


def initialize(db, prefix):
    db.execute(f'''CREATE TABLE IF NOT EXISTS {prefix}model_budget_owners (
        id TEXT PRIMARY KEY, pid INTEGER NOT NULL, process_started REAL NOT NULL,
        context TEXT, after_row INTEGER NOT NULL DEFAULT 0)''')


def own(db, prefix, identity):
    db.execute(f'INSERT INTO {prefix}model_budget_owners(id,pid,process_started) VALUES (?,?,?)',
               (identity, os.getpid(), psutil.Process().create_time()))


def attach(store, identity, context, after):
    from .model_budget_ledger import prefix
    with store.connection() as db:
        db.execute(f'UPDATE {prefix(store)}model_budget_owners SET context=?,after_row=? WHERE id=?',
                   (json.dumps(context), after, identity))


def alive(row):
    if row['pid'] is None:
        return False
    try:
        return abs(psutil.Process(row['pid']).create_time() - row['process_started']) < 0.01
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True


def receipt(row):
    if not row['context']:
        return 'unknown', 0
    from agent.token_ledger import connection
    context = json.loads(row['context'])
    # A copied/moved Profile must never read the original Profile's usage ledger.
    with connection() as db:
        calls = db.execute('SELECT state,total_tokens FROM token_usage_calls WHERE task_id=? AND rowid>?',
                           (context['task_id'], row['after_row'])).fetchall()
    confirmed = calls and all(call['state'] == 'confirmed' and call['total_tokens'] is not None for call in calls)
    return 'confirmed' if confirmed else 'unknown', sum(call['total_tokens'] or 0 for call in calls)


def recover(store):
    from .model_budget_ledger import prefix
    name = prefix(store)
    with store.connection() as db:
        rows = db.execute(f"SELECT u.id,o.pid,o.process_started,o.context,o.after_row FROM {name}model_budget_usage u "
                          f"LEFT JOIN {name}model_budget_owners o ON o.id=u.id WHERE u.state='pending'").fetchall()
    for row in rows:
        if alive(row):
            continue
        state, tokens = receipt(row)
        with store.connection() as db:
            db.execute(f"UPDATE {name}model_budget_usage SET state=?,tokens=? WHERE id=? AND state='pending'",
                       (state, tokens, row['id']))
