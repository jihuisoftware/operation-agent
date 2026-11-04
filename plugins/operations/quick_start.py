"""Durable first-run intent, drained by the existing Cron tick under its lease."""
import hashlib
import json

from .collection_ledger import load, save
from .policy import now_iso
from .store import encoded


def apply(store, body):
    from .blueprints import preview
    from .runtime import ensure_schedule
    request_id = body.get('request_id')
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
        raise ValueError('请求 ID 无效')
    if type(body.get('start')) is not bool:
        raise ValueError('开始选项无效')
    digest = hashlib.sha256(encoded(body).encode()).hexdigest()
    receipt = load(store, 'apply:' + request_id)
    if receipt:
        if receipt['hash'] != digest:
            raise ValueError('同一请求 ID 不能用于不同配置')
        version = receipt['version']
    else:
        result = preview(store, body)
        if result['blocking']:
            raise ValueError('；'.join(result['blocking']))
        policy = result['policy']
        policy['enabled'] = body['start'] or store.policy()[1]['enabled']
        policy['paused'] = store.policy()[1]['paused']
        existing = status(store)['run']
        if existing and existing['version'] == body['version'] and policy == store.policy()[1]:
            return {'version': body['version'], 'run': existing, 'reused': True}
        options = {'read_limit': 20, 'query_limit': 3} if body['start'] else None
        version = store.configure(policy, body['version'], request_id=request_id, request_hash=digest,
                                  first_run=options, activation=True)
    from .readiness import refresh
    refresh(store)
    job_id = ensure_schedule(store) if store.policy()[1]['enabled'] else None
    if body['start'] and job_id:
        from cron.jobs import update_job
        pending = load(store, 'quick:' + request_id)
        if pending and pending['state'] == 'pending':
            update_job(job_id, {'next_run_at': now_iso()})
    return {'version': version, 'job_id': job_id, 'run': load(store, 'quick:' + request_id)}


def status(store):
    with store.connection() as db:
        row = db.execute("SELECT id,data FROM objects WHERE kind='quick_run' ORDER BY created DESC LIMIT 1").fetchone()
        slot = 'manual:' + row['id'] if row else ''
        scope = (slot, len(slot) + 1, slot + ':')
        where = '(slot=? OR substr(slot,1,?)=?)'
        runs = [] if not row else [dict(r) for r in db.execute(f'SELECT * FROM runs WHERE {where} ORDER BY started,rowid', scope)]
        events = [] if not row else [dict(r) for r in db.execute(
            f"SELECT id,at,kind,data FROM events WHERE json_extract(data,'$.run_id') IN (SELECT id FROM runs WHERE {where}) ORDER BY id", scope)]
    for item in runs:
        item['attempt'] = int(item['slot'].rsplit(':resume:', 1)[1]) if ':resume:' in item['slot'] else 0
    result = {**json.loads(row['data']), 'id': row['id']} if row else None
    errors = [r for r in runs if r['state'] in {'failed', 'interrupted'}]
    errors.extend(e for e in events if 'error' in e['kind'] or json.loads(e['data']).get('state') in {'failed', 'interrupted'})
    if result and result['state'] == 'failed':
        errors.append({'kind': 'quick_run_error', 'detail': result.get('detail', '')})
    return {'run': result, 'steps': runs, 'events': events, 'errors': errors}


def drain(store, now):
    from .manual import run
    from .readiness import refresh
    with store.connection() as db:
        row = db.execute("SELECT id,data FROM objects WHERE kind='quick_run' AND json_extract(data,'$.state') IN ('pending','running') ORDER BY created LIMIT 1").fetchone()
    if not row:
        return None
    data = json.loads(row['data'])
    version, policy = store.policy()
    if policy['paused'] or not policy['enabled']:
        return '快速首轮等待计划恢复'
    if version != data['version']:
        data.update(state='cancelled', detail='规则已变化；首轮未重新启动')
    else:
        data['state'] = 'running'
        save(store, 'quick_run', row['id'], data)
        from .progress import bind
        bind(store, now, row['id'])
        store.run_options = data['options']
        refresh(store, now)
        try:
            detail = run(store, now, row['id'])
            with store.connection() as db:
                states = [r[0] for r in db.execute('SELECT state FROM runs WHERE slot=?', ('manual:' + row['id'],))]
            data.update(state='completed' if states and all(s == 'completed' for s in states) else 'partial', detail=detail)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("Quick first run failed")
            data.update(state='failed', detail=str(exc))
        finally:
            store.run_options = None
    if (load(store, row['id']) or {}).get('state') == 'cancelled':
        data.update(state='cancelled', detail='用户取消首轮，已完成记录仍保留；已提交动作需核对')
    data['ended'] = now_iso()
    save(store, 'quick_run', row['id'], data)
    if data.get('activation_boundary'):
        save(store, 'activation', 'plan-activation', {'after': data['ended']})
    return data['detail']
