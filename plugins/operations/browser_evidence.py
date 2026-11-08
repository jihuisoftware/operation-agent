"""Bounded, profile-local browser step evidence using the existing event/object journal."""
import base64
import hashlib
from io import BytesIO
import json
import re
import time
from urllib.parse import urlsplit, urlunsplit
from PIL import Image
from .policy import now_iso, local_day
from .store import encoded


def command_context(store):
    return {k: v for k, v in {'run_id': store.current_run_id, 'manual_run_id': store.manual_run_id,
                              'step_id': getattr(store, 'debug_step', None), 'resume_key': getattr(store, 'resume_key', None)}.items() if v}


def clean(value, depth=0):
    if depth > 6:
        return '[省略深层数据]'
    if isinstance(value, str):
        if value.startswith(('https://', 'http://')):
            url = urlsplit(value)
            value = urlunsplit((url.scheme, url.hostname or '', url.path, '', ''))
        return value[:4000]
    if isinstance(value, list):
        return [clean(v, depth + 1) for v in value[:100]]
    if isinstance(value, dict):
        return {k: clean(v, depth + 1) for k, v in list(value.items())[:60]
                if not re.search(r'password|cookie|authorization|token|secret', k, re.IGNORECASE)}
    return value


def screenshot(data):
    if not isinstance(data, str) or len(data) > 1_500_000:
        raise ValueError('截图超过保存上限')
    header, payload = data.split(',', 1)
    if header not in {'data:image/png;base64', 'data:image/jpeg;base64'}:
        raise ValueError('截图格式不支持')
    raw = base64.b64decode(payload, validate=True)
    with Image.open(BytesIO(raw)) as image:
        if image.format not in {'PNG', 'JPEG'} or image.width * image.height > 4_000_000:
            raise ValueError('截图尺寸或格式无效')
        image.verify()
    return 'browser-evidence:' + hashlib.sha256(raw).hexdigest(), data


def record_step(store, command_id, worker, body):
    sequence, phase = body.get('sequence'), body.get('phase')
    if type(sequence) is not int or not 1 <= sequence <= 100 or phase not in {'started', 'completed', 'failed'}:
        raise ValueError('步骤序号或状态无效')
    name = body.get('name', '')
    if not isinstance(name, str) or not re.fullmatch(r'[a-z_-]{1,60}', name):
        raise ValueError('步骤名称无效')
    if len(encoded(body)) > 1_550_000:
        raise ValueError('步骤记录过大')
    shot = screenshot(body['screenshot']) if body.get('screenshot') else None
    data = clean({k: v for k, v in body.items() if k != 'screenshot'})
    if store.scope:
        data.update(business_id=store.scope['business_id'], topic_id=store.scope['id'])
    if len(encoded(data)) > 32_000:
        raise ValueError('步骤文本过大')
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        command = db.execute('SELECT * FROM commands WHERE id=? AND worker=?', (command_id, worker)).fetchone()
        if body.get('phase') == 'started' and command:
            from .workspace_execution import check_running
            check_running(store, web=command['kind'] not in {'account', 'verify'}, db=db)
        if not command:
            raise ValueError('步骤不属于当前执行者')
        key = f'browser-step:{command_id}:{sequence}:{phase}'
        existing = db.execute('SELECT data FROM objects WHERE id=?', (key,)).fetchone()
        if existing:
            return json.loads(existing[0])
        if command['state'] != 'running' or command['expires'] < time.time():
            started = db.execute('SELECT data FROM objects WHERE id=?', (f'browser-step:{command_id}:{sequence}:started',)).fetchone()
            if phase == 'started' or not started or json.loads(started[0])['name'] != name:
                raise ValueError('任务已结束或过期，不能追加网页操作')
            data['late_evidence'] = True
        from .readiness import web_block_reason
        blocked = web_block_reason(db)
        if phase == "started" and blocked:
            raise ValueError(blocked)
        from .analysis_publication import check_step
        check_step(db, command, phase)
        payload = json.loads(command['payload'])
        if phase == 'started' and payload.get('human_review'):
            from .content_release import authorization
            version, policy = store.policy()
            if not authorization(store, db, payload, version, policy):
                raise ValueError('人工审核授权已失效，不能继续提交')
        cancelled = db.execute("SELECT 1 FROM objects WHERE id=? AND json_extract(data,'$.state')='cancelled'", (payload.get('manual_run_id', ''),)).fetchone()
        if phase == 'started' and command['kind'] != 'verify':
            from .batch_cancellation import check
            check(store, db=db, batch=payload.get('manual_run_id'))
            if cancelled:
                raise ValueError('批次已取消，不能追加网页操作')
        data.update(command_id=command_id, action_id=command['action_id'] or payload.get('verification_action_id'),
                    policy_version=payload['policy_version'], account_id=payload.get('account_id'),
                    debug_id=payload.get('manual_run_id'), run_id=payload.get('run_id'),
                    step_id=payload.get('step_id'), day=local_day(store.policy()[1]), at=now_iso())
        if shot:
            db.execute("INSERT OR IGNORE INTO objects VALUES (?, 'browser_evidence', ?, ?)",
                       (shot[0], encoded({'image': shot[1], 'command_id': command_id}), now_iso()))
            data['evidence_id'] = shot[0]
        db.execute("INSERT INTO objects VALUES (?, 'browser_step', ?, ?)", (key, encoded(data), now_iso()))
        db.execute("INSERT INTO events(at,kind,data) VALUES (?, 'browser_step', ?)", (now_iso(), encoded(data)))
    return data


def steps(store, action_id):
    with store.connection() as db:
        if not db.execute('SELECT 1 FROM actions WHERE id=?', (action_id,)).fetchone():
            raise ValueError('动作不存在')
        rows = db.execute("SELECT id,at,data FROM events WHERE kind='browser_step' AND json_extract(data,'$.action_id')=? ORDER BY id", (action_id,))
        return [{**json.loads(row['data']), 'event_id': row['id']} for row in rows]


def baseline(store, action_id):
    records = steps(store, action_id)
    candidates = [r.get('result') for r in records if r['name'] == 'baseline' and r['phase'] == 'completed']
    return candidates[-1] if candidates else None
