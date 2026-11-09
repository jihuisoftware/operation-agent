"""Account-wide publication evidence and reservation reuse without rewriting old attempts."""
from contextlib import closing
import json
import logging
import sqlite3

from .publication_attempts import guard, rows


def history(store, db, action):
    if not store.workspace:
        return []
    account = db.execute('SELECT account FROM directory.businesses WHERE id=?', (store.scope['business_id'],)).fetchone()[0]
    scopes = db.execute("SELECT c.topic_id,t.business_id,t.file,min(c.action_id) AS action_id FROM directory.account_claims c "
        "JOIN directory.topics t ON t.id=c.topic_id WHERE c.account_id=? AND c.kind='publish' AND c.topic_id!=? "
        "AND (c.target=? OR CASE WHEN json_valid(c.target) THEN json_extract(c.target,'$[0]') END=?) "
        'GROUP BY c.topic_id,t.business_id,t.file', (account, store.scope['id'], action['target'], action['target'])).fetchall()
    previous = []
    from .action_admission import ActionDeferred
    for scope in scopes:
        path = (store.workspace.root / scope['file']).resolve()
        if not path.is_relative_to(store.workspace.root.resolve()):
            raise ValueError('发布历史不属于当前配置空间')
        try:
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)) as other:
                other.row_factory = sqlite3.Row
                other.execute('BEGIN')
                saved = guard(other, action, scope=dict(scope))
                # A legacy claim without its source action cannot establish non-submission.
                exists = other.execute("SELECT 1 FROM actions WHERE kind='publish' AND json_extract(data,'$.target')=?", (action['target'],)).fetchone()
                if not exists:
                    raise ActionDeferred({'id': scope['action_id'], 'kind': 'publish', 'state': 'unknown'}, scope=dict(scope), publication=True)
                previous.extend({**row, 'topic_id': scope['topic_id']} for row in saved)
        except sqlite3.Error as exc:
            logging.getLogger(__name__).warning('Cannot inspect shared publication history', exc_info=True)
            raise ActionDeferred({'id': scope['action_id'], 'kind': 'publish', 'state': 'unknown'}, scope=dict(scope), publication=True) from exc
    return previous


def charge_key(store, db, action, identity, account, day, previous):
    from .workspace_execution import budget_day
    limits = json.loads(db.execute("SELECT data FROM directory.preferences WHERE id='limits'").fetchone()[0])
    shared_day = budget_day(store, day, limits)
    used = db.execute("SELECT coalesce(sum(amount),0) FROM directory.charges WHERE day=? AND kind='publish' AND account_id=?", (shared_day, account)).fetchone()[0]
    default = store.scope['id'] + ':' + identity
    if not 0 < used <= limits['publish']:
        return default
    candidates = [{**row, 'topic_id': store.scope['id']} for row in rows(db, action)] + previous
    for row in candidates:
        data = json.loads(row['data'])
        key = data.get('publication_charge_id') or row['topic_id'] + ':' + row['id']
        if db.execute("SELECT 1 FROM directory.charges WHERE id=? AND day=? AND kind='publish' AND account_id=?", (key, shared_day, account)).fetchone():
            return key
    return default


def reserve(store, db, action, identity, day, account):
    from .store import encoded
    from .workspace_execution import charge
    previous = history(store, db, action)
    key = charge_key(store, db, action, identity, account, day, previous)
    action['publication_charge_id'] = key
    # Keep one claim per attempt; readers accept old raw-digest claims as well.
    target = encoded([action['target'], identity])
    db.execute("INSERT OR IGNORE INTO directory.account_claims VALUES (?,'publish',?,?,?)", (account, action['target'], store.scope['id'], identity))
    db.execute("INSERT OR IGNORE INTO directory.account_claims VALUES (?,'publish',?,?,?)", (account, target, store.scope['id'], identity))
    charge(store, db, day, 'publish', identity=key, account=account)
    db.execute("INSERT OR IGNORE INTO directory.account_actions VALUES (?,?,?,'publish','queued')", (account, store.scope['id'], identity))
    return True
