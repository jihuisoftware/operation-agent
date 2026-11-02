"""Account workers heartbeat every owning topic and claim work in rotation."""
import json
import time


def poll(directory, account, worker, busy):
    catalog = directory.catalog()
    businesses = {b['id']: b['name'] for b in catalog['businesses'] if b['account'] == account}
    topics = [t for t in catalog['topics'] if t['business_id'] in businesses and not t['archived']]
    with directory.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        key = 'worker-cursor:' + account
        row = db.execute('SELECT data FROM preferences WHERE id=?', (key,)).fetchone()
        cursor = int(row[0]) if row else 0
        db.execute('INSERT OR REPLACE INTO preferences VALUES (?,?)', (key, str(cursor + 1)))
        db.execute('UPDATE account_holds SET seen=? WHERE account_id=? AND worker=?', (time.time(), account, worker))
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
        claimed = store.claim(worker, busy=busy)
        if claimed:
            command = {**claimed, 'scope': scope, 'topic_name': label}
    return {'command': command, 'latest_report': max(reports, key=lambda r: r['created']) if reports else None, 'publication_notices': notices}


def takeover(store, db, worker, active):
    account = db.execute('SELECT account FROM directory.businesses WHERE id=?', (store.scope['business_id'],)).fetchone()[0]
    held = db.execute('SELECT * FROM directory.account_holds WHERE account_id=?', (account,)).fetchone()
    if held and held['worker'] != worker and held['seen'] > time.time() - 15:
        raise ValueError('另一执行窗口正在人工接管，请在该窗口结束接管')
    db.execute('UPDATE directory.accounts SET held=? WHERE id=?', (int(active), account))
    if active:
        db.execute('INSERT OR REPLACE INTO directory.account_holds VALUES (?,?,?)', (account, worker, time.time()))
    else:
        db.execute('DELETE FROM directory.account_holds WHERE account_id=?', (account,))
