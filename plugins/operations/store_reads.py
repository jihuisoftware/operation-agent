"""Bounded state projections and lightweight worker liveness queries."""
import json
import time
from datetime import UTC, datetime


def objects(store, kind, day=None, *, limit=None):
    if limit is not None and (type(limit) is not int or limit < 0):
        raise ValueError('读取数量必须为非负整数')
    with store.connection() as db:
        return [{**json.loads(row['data']), 'id': row['id']} for row in db.execute(
            "SELECT id,data FROM objects WHERE kind=? AND (? IS NULL OR json_extract(data,'$.day')=?) ORDER BY created DESC LIMIT ?",
            (kind, day, day, -1 if limit is None else limit))]


def worker_status(db):
    seen = db.execute('SELECT max(seen) FROM workers').fetchone()[0]
    return {'online': seen is not None and seen > time.time() - 15,
            'last_seen': datetime.fromtimestamp(seen, UTC).isoformat() if seen is not None else None}


def online(store):
    with store.connection() as db:
        return worker_status(db)['online']


def snapshot(store):
    version, policy = store.policy()
    with store.connection() as db:
        tables = {name: [dict(r) for r in db.execute(f'SELECT * FROM {name} ORDER BY rowid DESC LIMIT 100')]
                  for name in ('runs', 'actions', 'events')}
    from .pause_origin import project_runs
    tables['runs'] = project_runs(store, tables['runs'])
    tables['actions'] = [{**a, 'target': json.loads(a['data'])['target']} for a in tables['actions']]
    if store.scope:
        owner = {'business_id': store.scope['business_id'], 'topic_id': store.scope['id']}
        tables = {name: [{**row, **owner} for row in rows] for name, rows in tables.items()}
    return {'version': version, 'policy': policy, 'online': online(store), **tables,
            **{kind: objects(store, kind, limit=100) for kind in ('source', 'asset', 'content', 'metric', 'report', 'task', 'inbox', 'brief', 'block', 'review')}}
