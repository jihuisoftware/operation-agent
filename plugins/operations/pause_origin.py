"""Stable interruption provenance, separate from runs that merely encounter it later."""
import json
from datetime import datetime, UTC

from .policy import now_iso

FIELDS = ('cause_at', 'cause_business_id', 'cause_topic_id', 'cause_command_id', 'cause_run_id', 'cause_stage', 'cause_step', 'cause_started_at',
          'sleep_started_at', 'sleep_resumed_at', 'power_epoch', 'dispatch_state', 'submitted')


def legacy_view(db, reason):
    """Old cause timestamps prove inheritance; they do not prove that a machine slept."""
    view = dict(reason)
    if view.get('cause_run_id') or not view.get('cause_at') or not view.get('run_id'):
        return view
    run = db.execute('SELECT started FROM runs WHERE id=?', (view['run_id'],)).fetchone()
    if not run or view['cause_at'] >= datetime.fromisoformat(run['started']).timestamp():
        return view
    view.update(inherited=True, cause_started_at=datetime.fromtimestamp(view['cause_at'], UTC).isoformat())
    first = db.execute("SELECT data FROM objects WHERE kind='execution_pause' AND json_extract(data,'$.cause_at')=? ORDER BY created LIMIT 1",
                       (view['cause_at'],)).fetchone()
    original = json.loads(first[0]) if first else {}
    source = db.execute('SELECT started FROM runs WHERE id=?', (original.get('run_id'),)).fetchone()
    if source and datetime.fromisoformat(source['started']).timestamp() <= view['cause_at'] and original['run_id'] != view['run_id']:
        view.update(cause_run_id=original['run_id'], cause_stage=original.get('stage'),
                    cause_business_id=original.get('business_id'), cause_topic_id=original.get('topic_id'))
    return view


def enrich(store, db, result, payload=None):
    value = dict(result)
    if value.get('error_code') == 'SYSTEM_SUSPENDED' and value.get('sleep_started_at'):
        value.setdefault('cause_at', value['sleep_started_at'])
    payload = payload or {}
    run_id = payload.get('run_id') or store.current_run_id
    if not value.get('cause_run_id') and run_id:
        run = db.execute('SELECT stage,started FROM runs WHERE id=?', (run_id,)).fetchone()
        value.update(cause_business_id=(store.scope or {}).get('business_id'), cause_topic_id=(store.scope or {}).get('id'), cause_run_id=run_id, cause_stage=run['stage'] if run else '',
                     cause_step=payload.get('step_id', ''), cause_started_at=(
                         datetime.fromtimestamp(value['cause_at'], UTC).isoformat() if value.get('cause_at') else now_iso()))
    return value


def project_runs(store, rows):
    from .execution_pause_view import describe
    with store.connection() as db:
        pauses = [json.loads(row[0]) for row in db.execute("SELECT data FROM objects WHERE kind='execution_pause'").fetchall()]
        result = []
        for row in rows:
            reason = next((p for p in pauses if row['id'] in {p.get('run_id'), p.get('id')}), None)
            if not reason and row['state'] == 'paused':
                earlier = [p for p in pauses if p.get('error') == row['detail'] and p.get('paused_at', '') <= row['started']]
                if earlier:
                    # Some historical scheduled publications never saved their own pause object.
                    prior = max(earlier, key=lambda p: p['paused_at'])
                    reason = {**prior, 'id': row['id'], 'run_id': row['id'], 'inherited': True}
            view = describe(store, reason, db) if reason and row['state'] == 'paused' else None
            result.append({**row, **({'historical_detail': row['detail'], 'detail': view['error'], 'pause': view} if view else {})})
    return result
