"""Inspectable occurrences; cancellation wins the same UNIQUE claim used by execution."""
from datetime import datetime, timedelta, UTC
import json
import uuid
from zoneinfo import ZoneInfo

from .occurrences import visible_occurrences
from .policy import now_iso
from .progress import STEPS

CANCEL_REASON = '人工取消本次步骤'


def upcoming(store, now=None):
    version, policy = store.policy()
    now = (now or datetime.now(UTC)).astimezone(ZoneInfo(policy['timezone']))
    from .readiness import refresh
    readiness = refresh(store, now)
    with store.connection() as db:
        existing = {(r['day'], r['stage'], r['slot']): dict(r) for r in db.execute('SELECT * FROM runs WHERE day>=?', ((now.date() - timedelta(days=1)).isoformat(),))}
    steps = []
    if policy['enabled']:
        for stage, due in visible_occurrences(store, policy, now):
            day, slot = due.date().isoformat(), due.strftime('%H:%M')
            row = existing.get((day, stage, slot))
            if row and row['state'] != 'cancelled':
                continue
            if stage == 'report' and day < now.date().isoformat() and store.objects('report', day):
                continue
            steps.append({**item(day, stage, slot, due.isoformat(), row['state'] if row else 'pending'), 'readiness': readiness[stage]})
    manual = pending_manual(store)
    return {'version': version, 'topic': policy['topic'], 'paused': policy['paused'],
            'timezone': policy['timezone'], 'steps': sorted(steps, key=lambda s: s['due']), 'manual': manual}


def item(day, stage, slot, due, state='pending', execution_id=None):
    return {'day': day, 'stage': stage, 'slot': slot, 'due': due, 'state': state,
            'title': STEPS[stage][0], 'intent': STEPS[stage][1], 'execution_id': execution_id}


def pending_manual(store):
    from cron.executions import live_inflight_execution
    from cron.task_history import detail
    from cron.jobs import get_job
    schedules = store.objects('schedule')
    if not schedules:
        return []
    job = get_job(schedules[0]['job_id'])
    execution = live_inflight_execution(job['id']) if job else None
    if not execution or execution['scheduled_instant'] is not None:
        return []
    record = detail(job, execution['id'])
    day = record['context'].get('day')
    if not day:
        return []
    return [item(day, step['id'].split(':', 1)[0], 'manual:' + execution['id'], execution['claimed_at'],
                 step['state'], execution['id']) for step in record['steps'] if step['state'] in {'pending', 'cancelled'}]


def cancel(store, body, now=None):
    from cron.task_history import cancel_pending_step
    view = upcoming(store, now)
    key = tuple(body.get(k) for k in ('day', 'stage', 'slot', 'execution_id'))
    found = next((s for s in [*view['steps'], *view['manual']]
                  if tuple(s[k] for k in ('day', 'stage', 'slot', 'execution_id')) == key), None)
    if not found or body.get('version') != view['version']:
        raise ValueError('步骤或规则已变化，请刷新后重试')
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT version FROM settings WHERE id=1').fetchone()[0] != body['version']:
            raise ValueError('规则已变化，请刷新后重试')
        row = db.execute('SELECT state FROM runs WHERE day=? AND stage=? AND slot=?', key[:3]).fetchone()
        if row and row['state'] != 'cancelled':
            raise ValueError('步骤已经开始或完成，不能取消待执行步骤')
        if not row:
            stamp = now_iso()
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?)',
                       (uuid.uuid4().hex, *key[:3], body['version'], 'cancelled', CANCEL_REASON, stamp, stamp))
            db.execute("INSERT INTO events(at,kind,data) VALUES (?,'step_cancelled',?)", (stamp, json.dumps(found, ensure_ascii=False)))
    if found['execution_id']:
        cancel_pending_step(found['execution_id'], f"{found['stage']}:{found['slot']}", CANCEL_REASON)
    return {'state': 'cancelled'}
