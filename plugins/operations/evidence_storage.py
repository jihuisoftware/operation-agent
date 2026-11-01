"""Profile-local evidence retention and bounded diagnostic exports."""
import base64
from datetime import datetime, UTC, timedelta
from io import BytesIO
import json
from zipfile import ZipFile, ZIP_DEFLATED
import re
from urllib.parse import urlsplit, urlunsplit
from .policy import now_iso
from .store import encoded

DEFAULT = {'days': 30, 'automatic': False}


def settings(store):
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE id='evidence-retention'").fetchone()
    return {**DEFAULT, **(json.loads(row[0]) if row else {})}


def configure(store, body):
    days, automatic = body.get('days'), body.get('automatic')
    if type(days) is not int or not 7 <= days <= 365 or type(automatic) is not bool:
        raise ValueError('保留期限为 7 至 365 天，自动清理需明确选择')
    store.put('evidence_settings', {'days': days, 'automatic': automatic}, 'evidence-retention')
    return settings(store)


def statistics(store):
    with store.connection() as db:
        categories = [dict(r) for r in db.execute("SELECT kind,count(*) AS count,sum(length(CAST(data AS BLOB))) AS bytes FROM objects "
                     "WHERE kind IN ('browser_step','browser_evidence','publication_snapshot','manual_conclusion') GROUP BY kind")]
        pages = db.execute('PRAGMA page_count').fetchone()[0]
        size = db.execute('PRAGMA page_size').fetchone()[0]
        free = db.execute('PRAGMA freelist_count').fetchone()[0]
    return {'settings': settings(store), 'categories': categories, 'database_bytes': pages * size, 'reusable_bytes': free * size}


def cleanup(store, *, now=None):
    now = now or datetime.now(UTC)
    config = settings(store)
    cutoff = (now - timedelta(days=config['days'])).isoformat()
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        eligible = db.execute("SELECT id,data FROM events WHERE kind='browser_step' AND at<? "
            "AND NOT EXISTS(SELECT 1 FROM actions WHERE actions.id=json_extract(events.data,'$.action_id') "
            "AND state NOT IN ('published','confirmed','confirmed_not_published','cancelled')) "
            "AND NOT EXISTS(SELECT 1 FROM commands WHERE commands.id=json_extract(events.data,'$.command_id') AND state IN ('queued','running'))", (cutoff,)).fetchall()
        for row in eligible:
            data = json.loads(row['data'])
            key = f"browser-step:{data['command_id']}:{data['sequence']}:{data['phase']}"
            db.execute("DELETE FROM objects WHERE id=? AND kind='browser_step'", (key,))
            db.execute('DELETE FROM events WHERE id=?', (row['id'],))
        removed = db.execute("DELETE FROM objects AS shot WHERE kind='browser_evidence' AND created<? "
            "AND NOT EXISTS(SELECT 1 FROM events,json_tree(events.data) j WHERE j.value=shot.id) "
            "AND NOT EXISTS(SELECT 1 FROM objects AS other,json_tree(other.data) j WHERE other.kind!='browser_evidence' AND j.value=shot.id) "
            "AND NOT EXISTS(SELECT 1 FROM actions,json_tree(actions.result) j WHERE j.value=shot.id) "
            "AND NOT EXISTS(SELECT 1 FROM actions WHERE actions.id=json_extract(shot.data,'$.action_id') AND state NOT IN ('published','confirmed','confirmed_not_published','cancelled'))", (cutoff,)).rowcount
        result = {'steps_deleted': len(eligible), 'screenshots_deleted': removed, 'at': now.isoformat(), 'cutoff': cutoff}
        db.execute("INSERT INTO events(at,kind,data) VALUES (?, 'evidence_cleanup', ?)", (now.isoformat(), encoded(result)))
        db.execute("INSERT OR REPLACE INTO objects VALUES ('evidence-cleanup', 'evidence_maintenance', ?, ?)", (encoded(result), now.isoformat()))
    return {**result, **statistics(store)}


def maybe_cleanup(store, now):
    if not settings(store)['automatic']:
        return
    with store.connection() as db:
        row = db.execute("SELECT created FROM objects WHERE id='evidence-cleanup'").fetchone()
    if not row or (now - datetime.fromisoformat(row[0])).total_seconds() >= 86400:
        cleanup(store, now=now)


def diagnostic(store, identity):
    from .browser_evidence import steps
    from .publication_snapshot import read
    with store.connection() as db:
        row = db.execute('SELECT * FROM actions WHERE id=?', (identity,)).fetchone()
        if not row:
            raise ValueError('动作不存在')
        action = dict(row)
        action['data'], action['result'] = json.loads(action['data']), json.loads(action['result'])
        conclusions = [json.loads(r[0]) for r in db.execute("SELECT data FROM objects WHERE kind='manual_conclusion' AND json_extract(data,'$.action_id')=?", (identity,))]
    data = {'action': action, 'steps': steps(store, identity), 'snapshot': read(store, identity), 'manual_history': conclusions, 'exported_at': now_iso()}
    payload = encoded(redact(data)).encode()
    if len(payload) > 10 * 1024 * 1024:
        raise ValueError('诊断记录过大，请按步骤复制所需日志')
    buffer = BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('diagnostic.json', payload)
        archive.writestr('说明.txt', '诊断包包含本动作台账、最终稿快照和网页步骤；不包含 Cookie、密钥、图片文件。截图引用可在应用中查看。\n')
    return {'name': f'operations-{identity[:16]}.zip', 'data': base64.b64encode(buffer.getvalue()).decode()}


def redact(value):
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items() if not re.search(r'password|cookie|authorization|token|secret', key, re.IGNORECASE)}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str) and value.startswith(('https://', 'http://')):
        url = urlsplit(value)
        return urlunsplit((url.scheme, url.hostname or '', url.path, '', ''))
    return value
