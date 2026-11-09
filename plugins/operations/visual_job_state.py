"""Process-generation leases and request receipts for resumable image work."""
import hashlib
import json
import time
import uuid

from .store import encoded
from .policy import now_iso

SESSION = uuid.uuid4().hex


def claim(store, identity):
    token = uuid.uuid4().hex
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        record = json.loads(db.execute('SELECT data FROM objects WHERE id=?', (identity,)).fetchone()[0])
        lease = db.execute('SELECT token,expires FROM leases WHERE id=?', (identity,)).fetchone()
        if lease and lease['expires'] > time.time() and record.get('worker_session') == SESSION:
            return None
        record.update(worker_session=SESSION, worker_token=token)
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(record), identity))
        db.execute('INSERT OR REPLACE INTO leases VALUES (?,?,?)', (identity, token, time.time() + 1800))
    return token


def owned(db, store, identity):
    owner = getattr(store, 'visual_worker', None)
    if not owner or owner[0] != identity:
        return True
    row = db.execute('SELECT token,expires FROM leases WHERE id=?', (identity,)).fetchone()
    return bool(row and row['token'] == owner[1] and row['expires'] > time.time())


def receipt(store, body, identity=None):
    key = 'visual-request:' + body['request_id']
    digest = hashlib.sha256(encoded(body).encode()).hexdigest()
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT data FROM objects WHERE kind='visual_request' AND id=?", (key,)).fetchone()
        if row:
            data = json.loads(row[0])
            if data['digest'] != digest:
                raise ValueError('同一组图请求不能修改内容或参数')
            return data['job_id']
        if identity:
            db.execute("INSERT INTO objects VALUES (?,'visual_request',?,?)", (key, encoded({'digest': digest, 'job_id': identity}), now_iso()))
    return None


def status(store, identity):
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT data FROM objects WHERE kind='visual_set' AND id=?", (identity,)).fetchone()
        if not row:
            raise ValueError('组图任务不存在于当前主题')
        record = json.loads(row[0])
        if record['state'] not in {'queued', 'running'}:
            return record
        lease = db.execute('SELECT token,expires FROM leases WHERE id=?', (identity,)).fetchone()
        if record.get('worker_session') == SESSION and lease and lease['expires'] > time.time():
            return record
        record.update(state='needs_attention', detail='组图服务已中断；已完成页面与调用次数保留，请手动重试未完成部分')
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(record), identity))
        db.execute('DELETE FROM leases WHERE id=? AND token=?', (identity, record.get('worker_token', '')))
        return record
