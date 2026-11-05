"""Business-owned resources mirrored into topic ledgers for existing submit checks."""
import json
from .policy import now_iso


def synchronize(store):
    if not store.workspace or store.scope['archived'] or store.scope['business_archived']:
        return False
    with store.connection() as db:
        imports, mirrors, current, policy = changes(db, store.scope)
        if not imports and not mirrors and policy == json.loads(current['data']):
            return False
        db.execute('BEGIN IMMEDIATE')
        # Re-read under the write reservation; another writer may have synchronized already.
        imports, mirrors, current, policy = changes(db, store.scope)
        business = store.scope['business_id']
        for row in imports:
            db.execute("INSERT OR IGNORE INTO directory.resources VALUES (?,'asset',?,?,?)", (business, row['id'], row['data'], row['created']))
        for row in mirrors:
            db.execute("INSERT INTO objects VALUES (?,'asset',?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (row['id'], row['data'], row['created']))
        changed = policy != json.loads(current['data'])
        if changed:
            version = current['version'] + 1
            db.execute('UPDATE settings SET version=?,data=? WHERE id=1', (version, json.dumps(policy, ensure_ascii=False)))
            db.execute("INSERT INTO objects VALUES (?,'policy',?,?)", (f'policy:{version}', json.dumps({'version': version, 'policy': policy}, ensure_ascii=False), now_iso()))
            db.execute("UPDATE actions SET state='cancelled' WHERE state='queued'")
            db.execute("UPDATE commands SET state='cancelled' WHERE state='queued'")
            from .workspace_execution import sync_actions
            sync_actions(store, db)
    return changed


def changes(db, scope):
    business = scope['business_id']
    local = {row['id']: dict(row) for row in db.execute("SELECT id,data,created FROM objects WHERE kind='asset'")}
    shared = {row['id']: dict(row) for row in db.execute("SELECT id,data,created FROM directory.resources WHERE business_id=? AND kind='asset'", (business,))}
    imports = [row for key, row in local.items() if key not in shared]
    mirrors = []
    for identity, row in shared.items():
        target = {**json.loads(row['data']), 'business_id': business, 'topic_id': scope['id']}
        if identity not in local or json.loads(local[identity]['data']) != target:
            mirrors.append({**row, 'data': json.dumps(target, ensure_ascii=False)})
    current = db.execute('SELECT version,data FROM settings WHERE id=1').fetchone()
    policy = json.loads(current['data'])
    category = db.execute('SELECT category FROM directory.businesses WHERE id=?', (business,)).fetchone()[0]
    if policy['business_theme'] != category:
        policy.update(business_theme=category, business_subtype='')
    for key in ('knowledge', 'brand'):
        row = db.execute('SELECT data FROM directory.resources WHERE business_id=? AND kind=? AND id=?', (business, key, key)).fetchone()
        if row:
            policy[key] = json.loads(row[0])
    return imports, mirrors, current, policy


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
