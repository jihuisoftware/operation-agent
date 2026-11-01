"""Keep a late publish receipt without reviving execution or overriding a later decision."""
import json


def recover(db, identity, worker, result):
    if result.get('state') not in {'submitted', 'published'}:
        return None
    row = db.execute("SELECT * FROM commands WHERE id=? AND worker=? AND kind='publish' AND state='unknown'", (identity, worker)).fetchone()
    if not row or not row['action_id']:
        return None
    action = db.execute("SELECT * FROM actions WHERE id=? AND state='unknown'", (row['action_id'],)).fetchone()
    latest = db.execute('SELECT id FROM commands WHERE action_id=? ORDER BY rowid DESC LIMIT 1', (row['action_id'],)).fetchone()
    if not action or latest[0] != identity or json.loads(action['result']).get('manual_verification'):
        return None
    if not result.get('publication'):
        result['state'] = 'submitted'
    result['late_receipt'] = True
    return row


def same(saved, result):
    previous = json.loads(saved)
    candidate = dict(result)
    if previous.get('late_receipt'):
        candidate['late_receipt'] = True
        if not candidate.get('publication'):
            candidate['state'] = 'submitted'
    return previous == candidate
