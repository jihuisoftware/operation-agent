"""Account-scoped, idempotent read-only wake probes. Never clear execution interlocks."""
import hashlib
import json
import time
import uuid
from datetime import datetime, UTC

from .store import encoded
from .policy import now_iso


def _text(body, key):
    value = body.get(key)
    if not isinstance(value, str) or not value or len(value) > 160:
        raise ValueError('唤醒检查参数无效：' + key)
    return value


def revalidate(directory, body):
    account, worker, epoch, request = (_text(body, key) for key in ('account_id', 'worker', 'wake_epoch', 'request_id'))
    catalog = directory.catalog()
    businesses = {b['id'] for b in catalog['businesses'] if b['account'] == account and not b['archived']}
    topic = next((t for t in catalog['topics'] if t['business_id'] in businesses and not t['archived']), None)
    if not topic:
        raise ValueError('当前Profile没有此账号的可用主题')
    store = directory.store(topic['business_id'], topic['id'])
    key = 'wake-probe:' + hashlib.sha256((account + ':' + epoch).encode()).hexdigest()
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        from .web_control import reason_for_account
        held = reason_for_account(db, account)
        if held:
            return {'state': 'deferred', 'detail': held}
        prior = db.execute('SELECT data FROM directory.preferences WHERE id=?', (key,)).fetchone()
        if prior:
            record = json.loads(prior[0])
        else:
            settings = db.execute('SELECT version,data FROM settings WHERE id=1').fetchone()
            version, policy = settings['version'], json.loads(settings['data'])
            if not policy['enabled'] or policy['paused']:
                return {'state': 'deferred', 'detail': '计划已暂停，等待手动检查'}
            identity = db.execute('SELECT identity FROM directory.accounts WHERE id=?', (account,)).fetchone()[0]
            command = uuid.uuid4().hex
            payload = {'wake_probe': epoch, 'resume_probe': True, 'policy_version': version,
                       'account_id': policy['account_id'] or identity, 'business_id': topic['business_id'], 'topic_id': topic['id']}
            db.execute("INSERT INTO commands VALUES (?,NULL,'account',?,'queued',NULL,?,'{}')",
                       (command, encoded(payload), time.time() + 120))
            record = {'command_id': command, 'topic_id': topic['id'], 'business_id': topic['business_id'],
                      'worker': worker, 'request_id': request, 'wake_epoch': epoch, 'created': now_iso(),
                      'expected_account': payload['account_id'], 'version': version}
            db.execute('INSERT INTO directory.preferences VALUES (?,?)', (key, encoded(record)))
    # The winning request can belong to a different topic on the shared account.
    owner = directory.store(record['business_id'], record['topic_id'])
    command = owner.command(record['command_id'])
    result = command['result']
    if command['state'] in {'queued', 'running'}:
        return {**record, 'state': 'checking', 'detail': '唤醒后正在只读检查账号'}
    valid = (command['state'] == 'done' and result.get('state') == 'logged_in' and result.get('account_id')
             and (not record['expected_account'] or result['account_id'] == record['expected_account'])
             and owner.policy()[0] == record['version'])
    checked = result.get('wake_checked_at', 0)
    with directory.connection() as db:
        latest = db.execute("SELECT record FROM account_logins WHERE account_id=? AND platform='xiaohongshu'", (account,)).fetchone()
    observed = json.loads(latest[0]) if latest else {}
    if observed.get('checked', 0) >= checked and observed.get('state') != 'unknown':
        valid = valid and observed.get('state') == 'logged_in' and observed.get('account_id') == result.get('account_id')
    status = {**record, 'state': 'ready' if valid else 'failed',
              'checked_at': datetime.fromtimestamp(checked, UTC).isoformat() if checked else now_iso(), 'checked_epoch': checked,
              'detail': '账号已确认；暂停批次仍需手动继续' if valid else '账号重验未通过，请检查页面后手动重试'}
    with directory.connection() as db:
        db.execute('INSERT OR REPLACE INTO preferences VALUES (?,?)', ('wake-status:' + account, encoded(status)))
    return status
