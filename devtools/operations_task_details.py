"""Task-scoped debug evidence, immutable model snapshots and append-only human notes."""
import json
import sqlite3

from fastapi import HTTPException
from plugins.operations.policy import now_iso
from plugins.operations.store import encoded

ARTIFACTS = ('source', 'organized_source', 'organization', 'organization_part', 'organization_merge',
             'analytics_report', 'industry_report', 'industry_batch', 'brief', 'content', 'content_revision_attempt', 'check', 'report', 'model_trace')


def context(store, batch, task):
    from .operations_debug import record, TASKS, require_enabled
    require_enabled()
    if task not in TASKS:
        raise HTTPException(404, '调试任务不存在')
    data = record(store, batch)
    if not data:
        raise HTTPException(404, '调试记录不存在')
    step = next((item for item in data.get('steps', []) if item['id'] == task), None)
    if data['task'] != task and not step:
        raise HTTPException(404, '此批次未执行所选任务')
    prefix = batch + ':' + task
    with store.connection() as db:
        runs = [dict(row) for row in db.execute('SELECT * FROM runs WHERE stage=? AND (slot=? OR slot=? OR substr(slot,1,?)=?) ORDER BY started',
                (TASKS[task][1], batch if data['task'] == task else prefix, prefix, len(prefix + ':resume:'), prefix + ':resume:'))]
    return data, step or {**data, 'id': task}, runs


def history(store, task, before=0):
    from .operations_debug import TASKS, require_enabled
    require_enabled()
    if task not in TASKS or before < 0:
        raise HTTPException(400, '调试任务或游标无效')
    with store.connection() as db:
        rows = db.execute("SELECT r.rowid,r.data FROM objects r WHERE r.kind='debug_run' AND NOT EXISTS(SELECT 1 FROM objects h "
                          "WHERE h.id='debug-history-hidden:'||r.id AND h.kind='debug_history_hidden') AND (?=0 OR r.rowid<?) AND "
                          "(json_extract(data,'$.task')=? OR EXISTS(SELECT 1 FROM json_each(data,'$.steps') s WHERE json_extract(s.value,'$.id')=?)) "
                          'ORDER BY rowid DESC LIMIT 31', (before, before, task, task)).fetchall()
    records = []
    for row in rows[:30]:
        value = json.loads(row['data'])
        records.append({key: value.get(key) for key in ('id', 'title', 'started', 'state', 'mode')})
    return {'runs': records, 'next': rows[29]['rowid'] if len(rows) > 30 else None}


def attempts(store, runs):
    from hermes_constants import get_hermes_home
    path = get_hermes_home() / 'state.db'
    if not path.exists() or not runs:
        return []
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='token_usage_calls'").fetchone():
            return []
        topic = store.scope['id'] if store.scope else ''
        return [dict(row) for row in db.execute("SELECT c.*,t.run_id FROM token_usage_calls c JOIN token_usage_tasks t ON t.id=c.task_id "
                "WHERE t.run_id IN (SELECT value FROM json_each(?)) AND t.topic_id=? ORDER BY c.started,c.id", (json.dumps(runs), topic))]


def view(store, batch, task, after=0, *, full=False):
    if after < 0:
        raise HTTPException(400, '日志游标无效')
    data, step, runs = context(store, batch, task)
    identities = json.dumps([row['id'] for row in runs])
    with store.connection() as db:
        events = db.execute("SELECT id,at,kind,data FROM events WHERE id>? AND json_extract(data,'$.debug_id')=? AND "
                            "(json_extract(data,'$.step_id')=? OR json_extract(data,'$.run_id') IN (SELECT value FROM json_each(?))) "
                            'ORDER BY id LIMIT ?', (after, batch, task, identities, -1 if full else 201)).fetchall()
        items = db.execute("SELECT id,kind,created,data FROM objects WHERE kind IN (SELECT value FROM json_each(?)) AND "
                           "json_extract(data,'$.run_id') IN (SELECT value FROM json_each(?)) ORDER BY created,rowid", (json.dumps(ARTIFACTS), identities)).fetchall()
        actions = [dict(row) for row in db.execute("SELECT * FROM actions WHERE json_extract(data,'$.manual_run_id')=? AND kind=? ORDER BY created", (batch, task))]
        notes = [json.loads(row[0]) for row in db.execute("SELECT data FROM objects WHERE kind='debug_note' AND json_extract(data,'$.batch_id')=? "
                                                        "AND json_extract(data,'$.task')=? ORDER BY created,rowid", (batch, task))]
    page = events if full else events[:200]
    artifacts = []
    for row in items:
        value = json.loads(row['data'])
        summary = {key: value.get(key) for key in ('title', 'state', 'started', 'ended', 'error', 'source_id', 'scope_topic') if value.get(key) is not None}
        artifacts.append({'id': row['id'], 'kind': row['kind'], 'created': row['created'], **({'data': value} if full else summary)})
    from .operations_debug_status import present_run, task_status
    presented = present_run(store, data)
    status = task_status(store, [presented])[task]
    shown = {**step, **{key: status[key] for key in ('state', 'detail', 'duration_ms', 'progress_at') if key in status}}
    return {'run': presented, 'task': task, 'step': shown, 'original_step': step, 'attempts': runs,
            'events': [{**dict(row), 'data': json.loads(row['data'])} for row in page], 'more': not full and len(events) > 200,
            'cursor': page[-1]['id'] if page else after, 'artifacts': artifacts, 'actions': actions,
            'model_attempts': attempts(store, [row['id'] for row in runs]), 'notes': notes,
            'policy': data.get('policy'), 'trace_notice': '新调试保存模型业务输入与返回；历史未保存的输入无法补回。'}


def artifact(store, batch, task, identity):
    _, _, runs = context(store, batch, task)
    with store.connection() as db:
        row = db.execute('SELECT kind,data FROM objects WHERE id=?', (identity,)).fetchone()
    if not row or row['kind'] not in ARTIFACTS:
        raise HTTPException(404, '执行产物不存在')
    value = json.loads(row['data'])
    if value.get('run_id') not in {run['id'] for run in runs}:
        raise HTTPException(404, '产物不属于本任务或批次')
    return {'id': identity, 'kind': row['kind'], 'data': value}


def note(store, batch, task, body):
    context(store, batch, task)
    text, request = body.get('text'), body.get('request_id')
    import re
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000 or not isinstance(request, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', request):
        raise HTTPException(400, '备注需为1～4000字，并提供有效请求标识')
    identity = 'debug-note:' + batch + ':' + task + ':' + request
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT data FROM objects WHERE id=?', (identity,)).fetchone()
        if previous:
            saved = json.loads(previous[0])
            if saved['text'] != text.strip():
                raise HTTPException(409, '同一备注请求不能修改内容')
            return saved
        value = {'id': identity, 'batch_id': batch, 'task': task, 'text': text.strip(), 'created': now_iso()}
        if store.scope:
            value.update(business_id=store.scope['business_id'], topic_id=store.scope['id'])
        db.execute("INSERT INTO objects VALUES (?, 'debug_note', ?, ?)", (identity, encoded(value), value['created']))
    return value
