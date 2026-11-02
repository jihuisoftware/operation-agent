"""Split legacy topic histories using recorded provenance, never current UI selection."""
import hashlib
import json
import sqlite3


def migrate(store):
    if not store.workspace or not store.scope['legacy']:
        return
    directory = store.workspace
    with store.connection() as db:
        if db.execute("SELECT 1 FROM directory.preferences WHERE id='migration-complete'").fetchone():
            return
        # SQLite's super-journal makes the original ledger + directory commit atomic.
        # WAL cannot guarantee that property across attached databases after power loss.
        db.execute('PRAGMA main.journal_mode=DELETE')
        db.execute('PRAGMA directory.journal_mode=DELETE')
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM directory.preferences WHERE id='migration-complete'").fetchone():
            return
        policy = json.loads(db.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
        objects = [dict(r) for r in db.execute('SELECT * FROM objects')]
        versions = {json.loads(r['data']).get('version'): json.loads(r['data']).get('policy', {}) for r in objects if r['kind'] == 'policy'}
        versions.setdefault(db.execute('SELECT version FROM settings WHERE id=1').fetchone()[0], policy)
        current = policy['topic']
        assignments = classify(db, objects, versions, current)
        names = set(assignments.values()) - {current}
        seed_shared(db, store, policy, assignments)
        # All archive copies are made from the committed original before deleting rows.
        # Their deterministic names are safe to rebuild after an interrupted migration.
        for name in sorted(names):
            identity = 'history-' + hashlib.sha256(name.encode()).hexdigest()[:24]
            relative = f'topics/{identity}.db'
            path = directory.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(store.path) as source, sqlite3.connect(path) as target:
                source.backup(target)
                prune(target, assignments, name)
                restore_references(target, objects, assignments, name)
                original = next((p for p in reversed(list(versions.values())) if p.get('topic') == name), policy)
                original = {**original, 'topic': name or '历史待归属', 'enabled': False, 'paused': True}
                target.execute('UPDATE settings SET data=? WHERE id=1', (json.dumps(original),))
                if target.execute("SELECT 1 FROM sqlite_master WHERE name='ownership'").fetchone():
                    target.execute('DELETE FROM ownership')
                target.execute('DELETE FROM leases')
                target.execute('DELETE FROM workers')
                target.commit()
                target.execute('VACUUM')
            db.execute('INSERT OR IGNORE INTO directory.topics(id,business_id,name,file,archived) VALUES (?,?,?,?,1)',
                       (identity, store.scope['business_id'], name or '历史待归属', relative))
        prune(db, assignments, current)
        restore_references(db, objects, assignments, current)
        db.execute("INSERT INTO directory.preferences VALUES ('migration-complete','true')")


def restore_references(db, objects, assignments, topic):
    """Keep explicitly pinned/cited sources and their reference pictures reachable."""
    wanted = set()
    source_map = {row['id']: row for row in objects if row['kind'] == 'source'}
    for row in objects:
        if assignments[('objects', row['id'])] != topic:
            continue
        data = json.loads(row['data'])
        wanted.update(data.get('source_ids', []))
        if row['kind'] == 'source_pin' and data.get('enabled'):
            wanted.add(data['source_id'])
        if row['kind'] == 'source':
            wanted.add(row['id'])
    images = set()
    for identity in wanted & source_map.keys():
        row = source_map[identity]
        data = json.loads(row['data'])
        if assignments[('objects', identity)] != topic:
            data.update(original_topic_label=data.get('scope_topic', ''), scope_topic=topic, legacy_reference=True)
        db.execute('INSERT OR IGNORE INTO objects VALUES (?,?,?,?)', (identity, row['kind'], json.dumps(data, ensure_ascii=False), row['created']))
        images.update(image['id'] for image in data.get('images', []) if image.get('id'))
    for row in objects:
        if row['kind'] == 'source_image' and row['id'] in images:
            db.execute('INSERT OR IGNORE INTO objects VALUES (?,?,?,?)', (row['id'], row['kind'], row['data'], row['created']))


def classify(db, objects, versions, current):
    assignments = {}
    for row in objects:
        data = json.loads(row['data'])
        topic = data.get('scope_topic')
        if topic is None and 'version' in data:
            topic = versions.get(data['version'], {}).get('topic')
        if row['kind'] in {'schedule', 'asset', 'activation', 'analysis_config'}:
            topic = current
        assignments[('objects', row['id'])] = topic if isinstance(topic, str) else ''
    for table in ('runs', 'actions'):
        for row in db.execute(f'SELECT * FROM {table}'):
            assignments[(table, row['id'])] = versions.get(row['version'], {}).get('topic', '')
    for row in db.execute('SELECT * FROM commands'):
        payload = json.loads(row['payload'])
        assignments[('commands', row['id'])] = assignments.get(('actions', row['action_id']), versions.get(payload.get('policy_version'), {}).get('topic', ''))
    for row in db.execute('SELECT * FROM events'):
        data = json.loads(row['data'])
        assignments[('events', row['id'])] = assignments.get(('runs', data.get('run_id')), versions.get(data.get('version'), {}).get('topic', ''))
    # Propagate reliable execution and evidence links; unlinked rows stay quarantined.
    for _ in range(3):
        for row in objects:
            key, data = ('objects', row['id']), json.loads(row['data'])
            if assignments[key]:
                continue
            refs = [assignments.get(('runs', data.get('run_id')), '')]
            refs += [assignments.get((table, data.get(field)), '') for table, field in (('commands', 'command_id'), ('actions', 'action_id'))]
            refs += [assignments.get(('objects', value), '') for value in data.get('source_ids', [])]
            known = set(refs) - {''}
            if len(known) == 1:
                assignments[key] = known.pop()
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='business_datasets'").fetchone():
        for row in db.execute('SELECT * FROM business_datasets'):
            assignments[('business_datasets', row['id'])] = json.loads(row['data']).get('scope_topic', '')
        for row in db.execute('SELECT id FROM business_uploads'):
            assignments[('business_uploads', row['id'])] = ''
    return assignments


def prune(db, assignments, topic):
    for table in ('objects', 'runs', 'actions', 'commands', 'events', 'business_datasets', 'business_uploads'):
        excluded = [identity for (kind, identity), owner in assignments.items() if kind == table and owner != topic]
        db.executemany(f'DELETE FROM {table} WHERE id=?', [(identity,) for identity in excluded])
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='business_batches'").fetchone():
        db.execute('DELETE FROM business_rows WHERE dataset_id NOT IN (SELECT id FROM business_datasets)')
        db.execute('DELETE FROM business_batches WHERE dataset_id NOT IN (SELECT id FROM business_datasets)')


def seed_shared(db, store, policy, assignments):
    account, topic = store.scope['account'], store.scope['id']
    budgets = {json.loads(r[0])['day']: json.loads(r[0])['used'] for r in db.execute("SELECT data FROM objects WHERE kind='collection_budget'")}
    for row in db.execute("SELECT json_extract(data,'$.day'),count(*) FROM objects WHERE kind='source' GROUP BY json_extract(data,'$.day')"):
        if row[0]:
            budgets.setdefault(row[0], row[1])
    for day, used in budgets.items():
        db.execute('INSERT OR IGNORE INTO directory.charges VALUES (?,?,?,?,?,?)', ('legacy-source:' + day, day, 'source', used, topic, ''))
    for row in db.execute("SELECT json_extract(data,'$.day'),count(*) FROM events WHERE kind='model_call' GROUP BY json_extract(data,'$.day')"):
        if row[0]:
            db.execute('INSERT OR IGNORE INTO directory.charges VALUES (?,?,?,?,?,?)', ('legacy-model:' + row[0], row[0], 'model', row[1], topic, ''))
    for row in db.execute("SELECT * FROM actions WHERE state!='cancelled'"):
        data = json.loads(row['data'])
        owner_name = assignments[('actions', row['id'])]
        action_topic = topic if owner_name == policy['topic'] else 'history-' + hashlib.sha256(owner_name.encode()).hexdigest()[:24]
        db.execute('INSERT OR IGNORE INTO directory.charges VALUES (?,?,?,?,?,?)', (topic + ':' + row['id'], row['day'], row['kind'], 1, topic, account))
        db.execute('INSERT OR IGNORE INTO directory.account_claims VALUES (?,?,?,?,?)', (account, row['kind'], data.get('target', row['target']), action_topic, row['id']))
        db.execute('INSERT OR IGNORE INTO directory.account_actions VALUES (?,?,?,?,?)', (account, action_topic, row['id'], row['kind'], row['state']))
    for row in db.execute('SELECT * FROM platform_logins ORDER BY checked'):
        evidence = db.execute('SELECT * FROM platform_login_evidence WHERE platform=? ORDER BY checked DESC LIMIT 1', (row['platform'],)).fetchone()
        db.execute('INSERT OR REPLACE INTO directory.account_logins VALUES (?,?,?,?)', (account, row['platform'], json.dumps(dict(row)), json.dumps(dict(evidence)) if evidence else None))
        if evidence and row['platform'] == 'xiaohongshu' and evidence['state'] == 'logged_in':
            db.execute('UPDATE directory.accounts SET identity=? WHERE id=?', (evidence['account_id'], account))
