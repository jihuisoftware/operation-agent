"""Durable read-attempt budget and retry state, scoped to one Profile database."""
import hashlib
import json

from .policy import now_iso
from .store import encoded


def save(store, kind, identity, data):
    with store.connection() as db:
        db.execute('INSERT INTO objects VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                   (identity, kind, encoded(data), now_iso()))


def load(store, identity):
    with store.connection() as db:
        row = db.execute('SELECT data FROM objects WHERE id=?', (identity,)).fetchone()
    return json.loads(row[0]) if row else None


def check(store, policy):
    from .plan_controls import check_cancelled
    check_cancelled(store)
    store.renew()
    if store.policy()[1] != policy or policy['paused'] or not policy['enabled']:
        raise ValueError('运营规则变更或已暂停，停止采集')


def budget(store, day):
    saved = load(store, 'collection-budget:' + day)
    return saved['used'] if saved else len(store.objects('source', day))


def reserve(store, policy, day, url, previous):
    """Charge before network I/O; a crash does not refund an attempted request."""
    check(store, policy)
    identity = 'collection-attempt:' + hashlib.sha256(f'{day}:{url}'.encode()).hexdigest()
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        current = json.loads(db.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
        if current != policy:
            raise ValueError('运营规则变更，停止采集')
        row = db.execute('SELECT data FROM objects WHERE id=?', (identity,)).fetchone()
        attempts = json.loads(row[0])['attempts'] if row else (previous or {}).get('attempts', 1 if previous else 0)
        if attempts >= 3:
            return None
        key = 'collection-budget:' + day
        saved = db.execute('SELECT data FROM objects WHERE id=?', (key,)).fetchone()
        used = json.loads(saved[0])['used'] if saved else db.execute(
            "SELECT count(*) FROM objects WHERE kind='source' AND json_extract(data,'$.day')=?", (day,)).fetchone()[0]
        if used >= policy['limits']['source']:
            return None
        from .workspace_execution import charge
        charge(store, db, day, 'source')
        for object_key, kind, data in ((key, 'collection_budget', {'day': day, 'used': used + 1}),
                                (identity, 'collection_attempt', {'day': day, 'url': url, 'attempts': attempts + 1})):
            db.execute('INSERT INTO objects VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                       (object_key, kind, encoded(data), now_iso()))
    return attempts + 1
