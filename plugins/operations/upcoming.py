"""Inspectable occurrences; cancellation wins the same UNIQUE claim used by execution."""
from datetime import datetime, UTC
import json
import uuid
from zoneinfo import ZoneInfo

from .policy import now_iso
from .progress import STEPS

CANCEL_REASON = '人工取消本次步骤'


def upcoming(store, now=None):
    version, policy = store.policy()
    now = (now or datetime.now(UTC)).astimezone(ZoneInfo(policy['timezone']))
    from .readiness import refresh
    readiness = refresh(store, now)
    from .daily_tasks import available
    steps = [{**item(day,stage,slot,now.isoformat()), 'readiness':readiness[stage]}
             for day,stage,slot in available(store,policy,now)] if policy['enabled'] else []
    if policy['enabled']:
        day = now.date().isoformat()
        if policy['modules']['report'] and now.strftime('%H:%M') < policy['work_end']:
            steps.append(item(day,'report','daily:close',datetime.fromisoformat(day+'T'+policy['work_end']).replace(tzinfo=now.tzinfo).isoformat()))
        with store.connection() as db:
            cancelled = list(db.execute("SELECT stage,slot FROM runs WHERE day=? AND state='cancelled' AND (slot LIKE 'daily:%' OR slot LIKE 'poll:%')", (day,)))
        for stage,slot in cancelled:
            steps = [s for s in steps if (s['day'],s['stage'],s['slot']) != (day,stage,slot)]
            steps.append(item(day,stage,slot,now.isoformat(),'cancelled'))
    manual = pending_manual(store)
    return {'version': version, 'topic': policy['topic'], 'paused': policy['paused'] or bool(store.workspace and store.workspace.blocked(store.scope)),
            'timezone': policy['timezone'], 'steps': sorted(steps, key=lambda s: s['due']), 'manual': manual}


def item(day, stage, slot, due, state='pending', execution_id=None):
    return {'day': day, 'stage': stage, 'slot': slot, 'due': due, 'state': state,
            'title': STEPS[stage][0], 'intent': STEPS[stage][1], 'execution_id': execution_id}


def pending_manual(store):
    if store.workspace:
        from .workspace_upcoming import pending
        return pending(store)
    return []


def cancel(store, body, now=None):
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
    return {'state': 'cancelled'}
