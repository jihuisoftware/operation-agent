"""Account workers heartbeat every owning topic and claim work in rotation."""
import json
import time


def poll(directory, account, worker, busy, *, takeover=None, wake_only=False):
    catalog = directory.catalog()
    businesses = {b['id']: b['name'] for b in catalog['businesses'] if b['account'] == account}
    topics = [t for t in catalog['topics'] if t['business_id'] in businesses and not t['archived']]
    with directory.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        key = 'worker-cursor:' + account
        row = db.execute('SELECT data FROM preferences WHERE id=?', (key,)).fetchone()
        cursor = int(row[0]) if row else 0
        db.execute('INSERT OR REPLACE INTO preferences VALUES (?,?)', (key, str(cursor + 1)))
        from .web_control import account_heartbeat
        control = account_heartbeat(db, account, worker, takeover, prefix='')
    if topics:
        start = cursor % len(topics)
        topics = topics[start:] + topics[:start]
    command, reports, notices = None, [], []
    for topic in topics:
        store = directory.store(topic['business_id'], topic['id'])
        scope = {'business_id': topic['business_id'], 'topic_id': topic['id']}
        label = businesses[topic['business_id']] + ' / ' + topic['name']
        with store.connection() as db:
            db.execute('INSERT OR REPLACE INTO workers VALUES (?,?)', (worker, time.time()))
            report = db.execute("SELECT id,created,json_extract(data,'$.day') AS day FROM objects WHERE kind='report' ORDER BY created DESC LIMIT 1").fetchone()
            if report:
                reports.append({**dict(report), 'record_id': report['id'], 'id': topic['id'] + ':' + report['id'], 'scope': scope, 'label': label})
            for row in db.execute("SELECT id,data FROM events WHERE kind='publication_notice' ORDER BY id DESC LIMIT 10"):
                notices.append({**json.loads(row['data']), 'id': topic['id'] + ':' + str(row['id']), 'scope': scope, 'label': label})
        if command or directory.blocked(store.scope):
            continue
        claimed = store.claim(worker, busy=busy, takeover=takeover, wake_only=wake_only)
        if claimed:
            command = {**claimed, 'scope': scope, 'topic_name': label}
    from .execution_pause import block
    execution_block = block(directory.store(topics[0]['business_id'], topics[0]['id'])) if topics else None
    return {'command': command, 'execution_block': execution_block, 'latest_report': max(reports, key=lambda r: r['created']) if reports else None,
            'publication_notices': notices, 'takeover': control}


def takeover(store, db, worker, active):
    account = db.execute('SELECT account FROM directory.businesses WHERE id=?', (store.scope['business_id'],)).fetchone()[0]
    from .web_control import account_takeover
    account_takeover(db, account, worker, active)
