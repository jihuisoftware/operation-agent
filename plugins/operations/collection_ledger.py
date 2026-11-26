"""Durable read-attempt budget and retry state, scoped to one Profile database."""
import hashlib
import json
import time

from .policy import DEFAULT, now_iso
from .store import encoded

_ANY_SOURCE = object()


def save(store, kind, identity, data):
    with store.connection() as db:
        write(store, db, kind, identity, data)


def write(store, db, kind, identity, data):
    from .run_scope import annotate
    data = annotate(store, data)
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
    return saved['used'] if saved else 0


def check_persisted(db, policy):
    # Legacy settings can omit new defaults without representing a rule change.
    current = {**DEFAULT, **json.loads(db.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])}
    if current != policy:
        raise ValueError('运营规则变更，停止采集')


def reserve(store, policy, day, url, *, recheck=False, claim=None, expected_source=_ANY_SOURCE):
    """Charge before network I/O; a crash does not refund an attempted request."""
    check(store, policy)
    identity = 'collection-attempt:' + hashlib.sha256(f'{day}:{url}'.encode()).hexdigest()
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        check_persisted(db, policy)
        row = db.execute('SELECT data FROM objects WHERE id=?', (identity,)).fetchone()
        attempts = json.loads(row[0])['attempts'] if row else 0
        if attempts >= 3:
            return None
        key = 'collection-budget:' + day
        saved = db.execute('SELECT data FROM objects WHERE id=?', (key,)).fetchone()
        totals = json.loads(saved[0]) if saved else {}
        used = totals.get('used', 0)
        if used >= policy['limits']['source']:
            return None
        if not admit_read(db, policy['topic'], url, claim, expected_source):
            return None
        from .workspace_execution import charge
        charge(store, db, day, 'source')
        for object_key, kind, data in ((key, 'collection_budget', {'day': day, 'used': used + 1, 'rechecks': totals.get('rechecks', 0) + int(recheck)}),
                                (identity, 'collection_attempt', {'day': day, 'url': url, 'attempts': attempts + 1})):
            db.execute('INSERT INTO objects VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                       (object_key, kind, encoded(data), now_iso()))
    return attempts + 1


def admit_read(db, topic, url, claim, expected_source):
    now = time.time()
    live = db.execute('SELECT 1 FROM collection_read_claims WHERE topic=? AND url=? AND expires>?', (topic, url, now)).fetchone()
    if live:
        return False
    if claim:
        row = db.execute('SELECT source_id FROM collection_urls WHERE topic=? AND url=?', (topic, url)).fetchone()
        if expected_source is not _ANY_SOURCE and (row[0] if row else None) != expected_source:
            return False
        db.execute('INSERT OR REPLACE INTO collection_read_claims VALUES (?,?,?,?)', (topic, url, claim, now + 600))
    return True


def release_read(db, topic, url, token):
    return db.execute('DELETE FROM collection_read_claims WHERE topic=? AND url=? AND token=?',
                      (topic, url, token)).rowcount
