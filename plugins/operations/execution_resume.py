"""One resume contract for debug, manual and scheduled executions; no replay of unknown submits."""
import json
import re

from .execution_pause import account_key, clear_block, load, block
from .policy import local_day, now_iso
from .store import encoded


def validate(store, data, body, db):
    if data.get('error_code') == 'REVALIDATION_REQUIRED':
        raise ValueError('启动检查期间上下文已变化，请按当前选择发起新批次')
    version, policy = store.policy()
    if data['state'] != 'paused' or type(body.get('expected_revision')) is not int or body['expected_revision'] != data['revision']:
        raise ValueError('暂停状态已变化，请刷新执行记录')
    if data['version'] != version or data['day'] != local_day(policy):
        raise ValueError('日期或规则已变化，请发起新批次；不会重新执行旧批次')
    linked = account_key(store, db)
    if store.workspace:
        linked = db.execute('SELECT account FROM directory.businesses WHERE id=?', (store.scope['business_id'],)).fetchone()[0]
    if data['account_link'] != linked:
        raise ValueError('账号关联已变化，不能继续旧批次')
    if not policy['enabled'] or policy['paused']:
        raise ValueError('请先解除计划暂停')
    from .action_admission import check_resume
    check_resume(db, data)
    return policy


def _owner_alive(receipt):
    import psutil
    if not receipt.get('pid') or receipt.get('process_started') is None:
        return False
    try:
        return abs(psutil.Process(receipt['pid']).create_time() - receipt['process_started']) < 0.01
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True


def recover(store):
    """Read-heavy status polling takes a write lock only for a proved abandoned owner."""
    with store.connection() as db:
        rows = db.execute("SELECT id,data FROM objects WHERE kind='execution_resume' "
                          "AND json_extract(data,'$.state') IN ('checking','running')").fetchall()
    abandoned = [row for row in rows if not _owner_alive(json.loads(row['data']))]
    if not abandoned:
        return
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        for row in abandoned:
            current = db.execute("SELECT data FROM objects WHERE id=? AND kind='execution_resume'", (row['id'],)).fetchone()
            if current and current[0] == row['data']:
                _recover_receipt(store, db, row['id'], json.loads(current[0]))


def _recover_receipt(store, db, receipt_id, receipt):
    from .execution_pause import set_block
    data = load(store, receipt['id'], db)
    message = '继续执行的进程已退出，已保留完成结果；请核对后手动继续'
    matching = data and ((data['state'] == 'running' and data['attempt'] == receipt['attempt'])
                         or (data['state'] == 'paused' and data['revision'] == receipt['expected_revision']))
    if matching:
        reason = block(store, db) or {'error_code': 'BROWSER_UNAVAILABLE', 'error': message}
        data.update(state='paused', revision=data['revision'] + 1, error_code=reason['error_code'],
                    error=reason['error'], paused_at=now_iso())
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(data), 'execution-pause:' + receipt['id']))
        if not block(store, db):
            set_block(store, db, reason)
    if receipt.get('lease_token'):
        db.execute("DELETE FROM leases WHERE id='account' AND token=?", (receipt['lease_token'],))
    result = {'id': receipt['id'], 'state': 'paused', 'detail': message,
              'revision': data['revision'] if data else None, 'attempt': receipt['attempt']}
    receipt.update(state='interrupted', ended=now_iso(), result=result)
    db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(receipt), receipt_id))


def _saved(receipt, body):
    if type(body.get('expected_revision')) is not int or receipt['expected_revision'] != body['expected_revision']:
        raise ValueError('同一继续请求不能用于不同版本')
    if receipt.get('state') == 'rejected':
        raise ValueError(receipt['error'])
    return receipt


def _begin(store, key, body):
    import os
    import time
    import psutil
    request = body.get('request_id')
    if not isinstance(request, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', request):
        raise ValueError('继续请求标识无效')
    receipt_id = 'execution-resume:' + key + ':' + request
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        saved = db.execute("SELECT data FROM objects WHERE id=? AND kind='execution_resume'", (receipt_id,)).fetchone()
        if saved:
            return _saved(json.loads(saved[0]), body), None
        if db.execute("SELECT 1 FROM objects WHERE kind='execution_resume' AND json_extract(data,'$.id')=? "
                      "AND json_extract(data,'$.state') IN ('checking','running')", (key,)).fetchone():
            raise ValueError('已有继续请求在执行，请等待其结果')
        data = load(store, key, db)
        if not data:
            raise ValueError('没有可恢复的暂停记录')
        validate(store, data, body, db)
        receipt = {'id': key, 'request_id': request, 'expected_revision': body['expected_revision'],
                   'attempt': data['attempt'], 'state': 'checking', 'receipt_id': receipt_id,
                   'pid': os.getpid(), 'process_started': psutil.Process().create_time(), 'started': time.time(),
                   'lease_token': store.lease_token, 'block_before': block(store, db)}
        db.execute("INSERT INTO objects VALUES (?,'execution_resume',?,?)", (receipt_id, encoded(receipt), now_iso()))
    return receipt, data


def _check_probe(store, db, receipt, identity):
    if block(store, db) != receipt['block_before']:
        raise ValueError('登录检查期间出现新的账号中断，请处理后重新点击继续')
    if store.workspace:
        row = db.execute("SELECT record FROM directory.account_logins WHERE account_id=? AND platform='xiaohongshu'",
                         (account_key(store, db),)).fetchone()
        observation = json.loads(row[0]) if row else None
    else:
        row = db.execute("SELECT * FROM platform_logins WHERE platform='xiaohongshu' ORDER BY checked DESC LIMIT 1").fetchone()
        observation = dict(row) if row else None
    if observation and observation['checked'] >= receipt['started']:
        negative = observation['state'] in {'logged_out', 'verification'}
        changed = observation['state'] == 'logged_in' and observation.get('account_id') != identity['account_id']
        if negative or changed:
            raise ValueError('登录检查期间账号状态已变化，请重新检查后继续')


def _activate(store, key, body, receipt, identity):
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        current = load(store, key, db)
        validate(store, current, body, db)
        _check_probe(store, db, receipt, identity)
        clear_block(store, db)
        current.update(state='running', revision=current['revision'] + 1, attempt=current['attempt'] + 1,
                       resumed_at=now_iso(), account_id=identity['account_id'])
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(current), 'execution-pause:' + key))
        receipt.update(state='running', attempt=current['attempt'])
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(receipt), receipt['receipt_id']))
    store.resume_attempt = current['attempt']
    store.start_preflight_done = True
    return current


def prepare(store, key, body):
    recover(store)
    receipt, data = _begin(store, key, body)
    if data is None:
        return receipt, True
    try:
        from .resume_validation import check
        check(store, data)
        from .workflow import browser
        identity = browser(store, 'account', {'resume_probe': True})
        if identity.get('state') != 'logged_in' or not identity.get('account_id'):
            raise ValueError('尚未确认当前登录账号，请登录后再继续')
        if data['account_id'] and identity['account_id'] != data['account_id']:
            raise ValueError('当前登录账号与暂停前不一致')
        check(store, data)
        return _activate(store, key, body, receipt, identity), False
    except Exception as exc:
        receipt.update(state='rejected', ended=now_iso(), error=str(exc))
        with store.connection() as db:
            db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(receipt), receipt['receipt_id']))
        raise


def complete(store, key, body, result):
    receipt_id = 'execution-resume:' + key + ':' + body['request_id']
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT data FROM objects WHERE id=?', (receipt_id,)).fetchone()
        receipt = _saved(json.loads(row[0]), body)
        if receipt['state'] != 'running':
            return receipt.get('result', receipt)
        receipt.update(state=result.get('state', 'completed'), result=result)
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(receipt), receipt_id))
        data = load(store, key, db)
        if data and data['state'] == 'running' and data['attempt'] == receipt['attempt']:
            data.update(state=result.get('state', 'completed'), ended=now_iso())
            db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(data), 'execution-pause:' + key))
    return result


def replay(store, key, body):
    recover(store)
    request = body.get('request_id', '')
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE id=? AND kind='execution_resume'", ('execution-resume:' + key + ':' + str(request),)).fetchone()
    if not row:
        return None
    data = _saved(json.loads(row[0]), body)
    return data.get('result') or {'id': key, 'state': data['state'], 'attempt': data['attempt']}


def paused_runs(store):
    recover(store)
    from .execution_pause_view import describe
    with store.connection() as db:
        rows = [json.loads(row[0]) for row in db.execute("SELECT data FROM objects WHERE kind='execution_pause'").fetchall()]
    result = []
    for row in rows:
        if row['state'] != 'paused':
            continue
        valid = row['day'] == local_day(store.policy()[1]) and row['version'] == store.policy()[0]
        result.append({**describe(store, row), 'execution_block': block(store), 'can_resume': valid,
                       'resume_reason': '' if valid else '日期或规则已变化，请按当前条件重新发起'})
    return result
