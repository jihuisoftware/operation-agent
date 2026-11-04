"""Resume ordinary work without losing batch options, completed stages or attempt history."""
import json
import uuid

from .execution_pause import load
from . import execution_resume
from .modules import TIMES
from .policy import now_iso
from .store import Store


def _batch(key):
    if key.startswith('manual:'):
        return key.removeprefix('manual:')
    return key if key.startswith('quick:') else None


def _latest(store, key, data):
    batch = _batch(key)
    with store.connection() as db:
        if batch:
            slot = 'manual:' + batch
            rows = db.execute('SELECT id,stage,state,detail,slot FROM runs WHERE day=? AND '
                              '(slot=? OR substr(slot,1,?)=?) ORDER BY started,rowid',
                              (data['day'], slot, len(slot) + 1, slot + ':')).fetchall()
        else:
            original = db.execute('SELECT slot FROM runs WHERE id=?', (key,)).fetchone()
            slot = original['slot'] if original else data['slot'].split(':resume:', 1)[0]
            rows = db.execute('SELECT id,stage,state,detail,slot FROM runs WHERE day=? AND stage=? AND '
                              '(slot=? OR substr(slot,1,?)=?) ORDER BY started,rowid',
                              (data['day'], data['stage'], slot, len(slot + ':resume:'), slot + ':resume:')).fetchall()
    return {row['stage']: dict(row) for row in rows}


def _options(store, batch):
    if not batch or not batch.startswith('quick:'):
        return store.run_options
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE id=? AND kind='quick_run'", (batch,)).fetchone()
    if not row:
        raise ValueError('首次执行记录缺失，不能扩大范围继续')
    quick = json.loads(row[0])
    if quick['state'] == 'cancelled':
        raise ValueError('首次执行已取消，不能继续')
    return dict(quick['options'])


def _state(steps, attempt_steps, pause):
    if pause['state'] == 'paused':
        return 'paused', pause['error']
    failures = [row['detail'] for row in steps if row['state'] == 'failed']
    if failures:
        return 'failed', '；'.join(failures)
    incomplete = [row['detail'] for row in steps if row['state'] != 'completed']
    if incomplete or not attempt_steps:
        return 'needs_attention', '；'.join(incomplete) or '没有可继续的未完成步骤，请核对原执行记录'
    return 'completed', '已继续未完成步骤'


def _continue(store, key, body, data):
    policy = store.policy()[1]
    old = _latest(store, key, data)
    stages = ([stage for stage in TIMES if policy['modules'][stage] and old.get(stage, {}).get('state') not in {'completed', 'skipped', 'failed'}]
              if _batch(key) else [data['stage']])
    from .runtime import _execute
    from .execution_pause import needs_account
    store.account_required = any(needs_account(policy, stage) for stage in stages)
    attempted = []
    for stage in stages:
        run = store.start_run(data['day'], stage, f"{data['slot']}:resume:{data['attempt']}", data['version'])
        if not run:
            continue
        _execute(store, policy, data['day'], data['version'], stage, run)
        with store.connection() as db:
            attempted.append(dict(db.execute('SELECT id,stage,state,detail FROM runs WHERE id=?', (run,)).fetchone()))
        if load(store, key)['state'] == 'paused':
            break
    latest = _latest(store, key, data)
    steps = [latest[stage] for stage in TIMES if stage in latest]
    state, detail = _state(steps, attempted, load(store, key))
    store.report_phase = state
    from .report import daily_report
    daily_report(store, data['day'])
    result = {'id': key, 'state': state, 'attempt': data['attempt'], 'ended': now_iso(),
              'steps': steps, 'attempt_steps': attempted, 'detail': detail}
    _finish_quick(store, key, result)
    return execution_resume.complete(store, key, body, result)


def _finish_quick(store, key, result):
    batch = _batch(key)
    if not batch or not batch.startswith('quick:'):
        return
    from .store import encoded
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT data FROM objects WHERE id=? AND kind='quick_run'", (batch,)).fetchone()
        quick = json.loads(row[0])
        quick.update(resume_result=result, resume_attempt=result['attempt'], ended=result['ended'])
        if quick['state'] != 'cancelled':
            quick.update(state='partial' if result['state'] == 'needs_attention' else result['state'], detail=result['detail'])
        db.execute("UPDATE objects SET data=? WHERE id=? AND kind='quick_run'", (encoded(quick), batch))


def resume(key, body, store=None):
    store = store or Store()
    previous = execution_resume.replay(store, key, body)
    if previous:
        return previous
    if key.startswith('debug:'):
        raise ValueError('调试批次请从任务调试页继续')
    token = 'resume:' + uuid.uuid4().hex
    if not store.lease(token):
        raise ValueError('已有任务执行中，本次继续未启动')
    previous_options, previous_batch = store.run_options, store.manual_run_id
    previous_key = getattr(store, 'resume_key', None)
    previous_attempt = getattr(store, 'resume_attempt', 0)
    previous_phase = getattr(store, 'report_phase', 'completed')
    previous_required = getattr(store, 'account_required', False)
    store.resume_key = key
    batch = _batch(key)
    if batch:
        store.manual_run_id = batch
    try:
        store.run_options = _options(store, batch)
        data, repeated = execution_resume.prepare(store, key, body)
        if repeated:
            return data.get('result', data)
        return _continue(store, key, body, data)
    finally:
        store.run_options, store.manual_run_id = previous_options, previous_batch
        store.resume_key = previous_key
        store.resume_attempt, store.report_phase = previous_attempt, previous_phase
        store.account_required = previous_required
        store.release(token)
