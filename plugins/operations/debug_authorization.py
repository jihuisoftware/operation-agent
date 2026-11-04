"""Read one-run grants created by the authenticated, source-only debug endpoint."""
import json
import time

import psutil

from .modules import ACTION_MODULE
from .policy import local_day


def grant_id(batch):
    return 'debug-authorization:' + batch


def _scope_matches(store, db, grant):
    if grant.get('database') != str(store.path.resolve()):
        return False
    scope = grant.get('scope')
    if not scope:
        return store.scope is None
    if not store.scope or scope['business_id'] != store.scope['business_id'] or scope['topic_id'] != store.scope['id']:
        return False
    account = db.execute('SELECT account FROM directory.businesses WHERE id=?', (scope['business_id'],)).fetchone()
    return bool(account and account[0] == scope['account'])


def _live_batch(db, grant, version, kind, policy):
    if grant['version'] != version or kind not in grant['actions'] or grant['day'] != local_day(policy):
        return False
    row = db.execute("SELECT data FROM objects WHERE id=? AND kind='debug_run'", (grant['batch'],)).fetchone()
    if not row:
        return False
    batch = json.loads(row[0])
    if batch['state'] != 'running' or batch.get('mode') != 'quick' or batch.get('action_mode') != 'execute_once':
        return False
    lease = db.execute("SELECT 1 FROM leases WHERE id='account' AND token=? AND expires>?", (grant['batch'], time.time())).fetchone()
    if not lease:
        return False
    try:
        return psutil.Process(batch['pid']).create_time() == batch['process_started']
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def read_grant(store, db, identity, version, kind, policy):
    row = db.execute("SELECT data FROM objects WHERE id=? AND kind='debug_action_grant'", (identity,)).fetchone()
    if not row:
        return None
    grant = json.loads(row[0])
    if _scope_matches(store, db, grant) and _live_batch(db, grant, version, kind, policy):
        return grant
    return None


def current_grant(store, db, version, kind, policy):
    batch = getattr(store, 'debug_id', None)
    if not batch or batch != store.manual_run_id or batch != store.lease_token:
        return None
    run = db.execute('SELECT stage,slot FROM runs WHERE id=?', (store.current_run_id,)).fetchone()
    if not run or run['stage'] != ACTION_MODULE.get(kind) or not (run['slot'] == batch or run['slot'].startswith(batch + ':')):
        return None
    return read_grant(store, db, grant_id(batch), version, kind, policy)


def authorized(store, policy, kind):
    if not getattr(store, 'debug_id', None):
        return False
    with store.connection() as db:
        version = db.execute('SELECT version FROM settings WHERE id=1').fetchone()[0]
        return bool(current_grant(store, db, version, kind, policy))


def allowed(store, policy, kind):
    return policy['allowed'][kind] or authorized(store, policy, kind)


def action_limit(store, policy, kind):
    limit = policy['limits'][kind]
    return min(limit, 1) if authorized(store, policy, kind) else limit


def model_policy(store, policy, kind):
    if not authorized(store, policy, kind):
        return policy
    return {**policy, 'allowed': {**policy['allowed'], kind: True},
            'limits': {**policy['limits'], kind: min(policy['limits'][kind], 1)}}


def reservation_policy(store, db, policy, action, version):
    action.pop('debug_authorization', None)
    grant = current_grant(store, db, version, action['kind'], policy)
    if not grant:
        batch = getattr(store, 'debug_id', None)
        row = db.execute("SELECT data FROM objects WHERE id=? AND kind='debug_run'", (batch,)).fetchone() if batch else None
        if row and json.loads(row[0]).get('action_mode') == 'execute_once':
            raise ValueError('本次快速实测授权已失效，请重新发起')
        return policy
    identity = grant_id(grant['batch'])
    count = db.execute("SELECT count(*) FROM actions WHERE kind=? AND json_extract(data,'$.debug_authorization')=?", (action['kind'], identity)).fetchone()[0]
    if count >= grant['max_per_kind']:
        raise ValueError('每种外部动作在本次快速实测中最多执行 1 次')
    action['debug_authorization'] = identity
    return {**policy, 'allowed': {**policy['allowed'], action['kind']: True}}


def may_dispatch(store, db, command, action, version, policy):
    if command['kind'] not in {'publish', 'interact'}:
        return True
    data = json.loads(action['data'])
    identity = data.get('debug_authorization')
    if not identity or read_grant(store, db, identity, version, data['kind'], policy):
        return True
    db.execute("UPDATE commands SET state='cancelled' WHERE id=?", (command['id'],))
    db.execute("UPDATE actions SET state='cancelled',result=? WHERE id=?", (json.dumps({'state': 'cancelled', 'evidence': '本次调试授权已失效，未派发'}), action['id']))
    from .workspace_execution import sync_actions
    sync_actions(store, db)
    return False
