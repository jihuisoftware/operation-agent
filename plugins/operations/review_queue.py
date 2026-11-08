"""Durable, read-only review jobs on the existing Desktop queue and Cron tick."""
from datetime import datetime, UTC, timedelta
import hashlib
import json
import time
import uuid
from .store import encoded
from .policy import now_iso


def fingerprint(result):
    return hashlib.sha256(encoded(result).encode()).hexdigest()


def load(db, identity):
    row = db.execute('SELECT data FROM objects WHERE id=?', ('tracking:' + identity,)).fetchone()
    return json.loads(row[0]) if row else {}


def save(db, identity, data):
    db.execute("INSERT INTO objects VALUES (?, 'publication_tracking', ?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
               ('tracking:' + identity, encoded(data), now_iso()))


def schedule(db, identity, result, *, initial=False, now=None):
    now = now or datetime.now(UTC)
    previous = {} if initial else load(db, identity)
    attempts = previous.get('attempts', 0) + (0 if initial else 1)
    observation = result.get('last_check', result)
    publication = observation.get('publication', {})
    reason = 'network' if observation.get('error') else 'unconfirmed'
    if publication.get('platform') == 'reviewing' and not observation.get('error'):
        reason = 'reviewing'
    if publication.get('content') == 'mismatch' or publication.get('platform') == 'rejected':
        reason = 'mismatch' if publication.get('content') == 'mismatch' else 'rejected'
    done = result.get('state') in {'published', 'confirmed'}
    first = previous.get('started_at') or now.isoformat()
    overdue = (now - datetime.fromisoformat(first)).total_seconds() > 7 * 86400
    attention = reason in {'mismatch', 'rejected'} or overdue or (attempts >= 8 and reason != 'reviewing')
    minutes = min(60, (15 if reason == 'reviewing' else 2 if reason == 'network' else 5) * 2 ** min(attempts, 5))
    state = 'done' if done else 'needs_attention' if attention else 'active'
    data = {**previous, 'action_id': identity, 'attempts': attempts, 'reason': reason, 'state': state,
            'started_at': first, 'checked_at': now.isoformat(),
            'next_check_at': (now + timedelta(minutes=0 if initial else minutes)).isoformat() if state == 'active' else None}
    old_status = previous.get('platform')
    status = result.get('publication', {}).get('platform')
    data['platform'] = status
    save(db, identity, data)
    if status in {'published', 'rejected'} and status != old_status:
        event = {'action_id': identity, 'platform': status, 'at': now.isoformat()}
        db.execute("INSERT INTO events(at,kind,data) VALUES (?, 'publication_notice', ?)", (now.isoformat(), encoded(event)))
    return data


def queue(db, row, version, *, now=None, force=False):
    now = now or datetime.now(UTC)
    identity = row['id']
    current = load(db, identity)
    existing = db.execute("SELECT id FROM commands WHERE kind='verify' AND state IN ('queued','running') "
                          "AND json_extract(payload,'$.verification_action_id')=?", (identity,)).fetchone()
    if existing:
        return existing[0]
    if not force and current:
        if current['state'] != 'active' or datetime.fromisoformat(current['next_check_at']) > now:
            return None
    if row['state'] not in {'submitted', 'unknown'}:
        raise ValueError('只有待核对的提交可发起只读检查')
    result = json.loads(row['result'])
    baseline = result.get('baseline')
    if not baseline:
        event = db.execute("SELECT data FROM events WHERE kind='browser_step' AND json_extract(data,'$.action_id')=? "
                           "AND json_extract(data,'$.name')='baseline' AND json_extract(data,'$.phase')='completed' ORDER BY id DESC LIMIT 1", (identity,)).fetchone()
        baseline = json.loads(event[0]).get('result') if event else None
    command = uuid.uuid4().hex
    payload = {**json.loads(row['data']), 'policy_version': version, 'result_url': result.get('url'),
               'previous_result': result, 'baseline': baseline, 'verification_action_id': identity,
               'verification_revision': fingerprint(result)}
    db.execute("INSERT INTO commands VALUES (?,NULL,'verify',?,'queued',NULL,?,'{}')",
               (command, encoded(payload), time.time() + 180))
    save(db, identity, {**current, 'action_id': identity, 'state': 'queued', 'command_id': command,
                       'attempts': current.get('attempts', 0), 'started_at': current.get('started_at', now.isoformat()),
                       'next_check_at': now.isoformat(), 'reason': current.get('reason', 'unconfirmed')})
    return command


def accept(db, command, result):
    from .publication_observations import merge, previous_facts
    payload = json.loads(command['payload'])
    identity = payload.get('verification_action_id')
    if not identity:
        return
    row = db.execute('SELECT * FROM actions WHERE id=?', (identity,)).fetchone()
    if not row or row['state'] not in {'submitted', 'unknown'} or fingerprint(json.loads(row['result'])) != payload.get('verification_revision'):
        return  # A later human decision always wins over an in-flight read.
    previous = previous_facts(db, row)
    if not result.get('error') and result.get('state') in {'submitted', 'published', 'confirmed'}:
        previous = {k: v for k, v in previous.items() if k not in {'error', 'error_code'}}
    checked_at = now_iso()
    merged = merge(previous, result, checked_at)
    if merged.get('state') not in {'published', 'confirmed', 'submitted', 'unknown'}:
        merged['state'] = row['state']
    merged.update(verified_at=checked_at, verified_by='page')
    db.execute('UPDATE actions SET state=?,result=? WHERE id=?', (merged['state'], encoded(merged), identity))
    schedule(db, identity, merged)


def request_check(store, identity):
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM actions WHERE id=?', (identity,)).fetchone()
        if not row:
            raise ValueError('动作不存在')
        cfg = db.execute('SELECT * FROM settings WHERE id=1').fetchone()
        policy = json.loads(cfg['data'])
        if not policy['enabled'] or policy['paused']:
            raise ValueError('请先结束人工接管并恢复运营规则，再核对')
        action = json.loads(row['data'])
        if policy['account_id'] and action['account_id'] != policy['account_id']:
            raise ValueError('当前配置账号与动作不匹配')
        return {'command_id': queue(db, row, cfg['version'], force=True)}


def mark_running(db, command):
    identity = json.loads(command['payload']).get('verification_action_id')
    if identity:
        current = load(db, identity)
        save(db, identity, {**current, 'state': 'checking'})
