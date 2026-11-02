"""Business-owned resources mirrored into topic ledgers for existing submit checks."""
import json
from .policy import now_iso


def synchronize(store):
    if not store.workspace or store.scope['archived'] or store.scope['business_archived']:
        return
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        business = store.scope['business_id']
        # Existing authorized assets become resources of their original business.
        for row in db.execute("SELECT id,data,created FROM objects WHERE kind='asset'").fetchall():
            db.execute("INSERT OR IGNORE INTO directory.resources VALUES (?,'asset',?,?,?)", (business, row['id'], row['data'], row['created']))
        for row in db.execute("SELECT * FROM directory.resources WHERE business_id=? AND kind='asset'", (business,)).fetchall():
            db.execute("INSERT INTO objects VALUES (?,'asset',?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (row['id'], row['data'], row['created']))
        current = db.execute('SELECT version,data FROM settings WHERE id=1').fetchone()
        policy = json.loads(current['data'])
        category = db.execute('SELECT category FROM directory.businesses WHERE id=?', (business,)).fetchone()[0]
        if policy['business_theme'] != category:
            policy.update(business_theme=category, business_subtype='')
        for key in ('knowledge', 'brand'):
            row = db.execute('SELECT data FROM directory.resources WHERE business_id=? AND kind=? AND id=?', (business, key, key)).fetchone()
            if row and policy[key] != json.loads(row[0]):
                policy[key] = json.loads(row[0])
        if policy != json.loads(current['data']):
            version = current['version'] + 1
            db.execute('UPDATE settings SET version=?,data=? WHERE id=1', (version, json.dumps(policy, ensure_ascii=False)))
            db.execute("INSERT INTO objects VALUES (?,'policy',?,?)", (f'policy:{version}', json.dumps({'version': version, 'policy': policy}, ensure_ascii=False), now_iso()))
            db.execute("UPDATE actions SET state='cancelled' WHERE state='queued'")
            db.execute("UPDATE commands SET state='cancelled' WHERE state='queued'")
            from .workspace_execution import sync_actions
            sync_actions(store, db)


def save_policy(store, db, policy):
    if store.workspace:
        db.execute('UPDATE directory.businesses SET category=? WHERE id=?', (policy['business_theme'], store.scope['business_id']))
        for key in ('knowledge', 'brand'):
            db.execute('INSERT OR REPLACE INTO directory.resources VALUES (?,?,?,?,?)', (store.scope['business_id'], key, key, json.dumps(policy[key], ensure_ascii=False), now_iso()))


def save_asset(store, identity):
    if not store.workspace:
        return
    with store.connection() as db:
        row = db.execute("SELECT * FROM objects WHERE id=? AND kind='asset'", (identity,)).fetchone()
        db.execute("INSERT OR REPLACE INTO directory.resources VALUES (?,'asset',?,?,?)", (store.scope['business_id'], identity, row['data'], row['created']))
