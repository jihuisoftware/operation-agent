"""One Cron dispatcher, durable per-topic manual requests and fair topic rotation."""
from datetime import UTC, datetime
import json
import logging


def dispatch(now=None):
    from .workspaces import Workspaces, bind_scope
    from .runtime import tick
    directory = Workspaces()
    now = now or datetime.now(UTC)
    catalog = directory.catalog()
    from .manual import cron_request_id
    original = directory.store()
    legacy_request = cron_request_id(original)
    if legacy_request:
        with directory.connection() as db:
            pending = db.execute("SELECT 1 FROM requests WHERE state IN ('pending','running')").fetchone()
        if not pending:
            request_run(original, legacy_request)
    topics = [t for t in catalog['topics'] if not t['archived']]
    with directory.connection() as db:
        row = db.execute("SELECT data FROM preferences WHERE id='cursor'").fetchone()
        cursor = int(row[0]) if row else 0
        db.execute("INSERT OR REPLACE INTO preferences VALUES ('cursor',?)", (str(cursor + 1),))
    if topics:
        start = cursor % len(topics)
        topics = topics[start:] + topics[:start]
    results = []
    for topic in topics:
        with bind_scope(topic['business_id'], topic['id']):
            store = directory.store(topic['business_id'], topic['id'])
            if directory.blocked(store.scope):
                continue
            with directory.connection() as db:
                request = db.execute("SELECT * FROM requests WHERE topic_id=? AND state IN ('pending','running') ORDER BY rowid LIMIT 1", (topic['id'],)).fetchone()
                if request:
                    db.execute("UPDATE requests SET state='running' WHERE id=? AND topic_id=?", (request['id'], topic['id']))
            try:
                detail = tick(store, now, request_id=request['id'] if request else None, scheduled=True)
                state = 'pending' if detail in {'已有运营任务执行中', '手动批次执行中'} else 'completed'
            except Exception as exc:
                logging.getLogger(__name__).exception('Topic dispatcher failed: %s', topic['id'])
                detail, state = str(exc), 'failed'
                store.event('dispatcher_error', {'error': detail})
            if request:
                with directory.connection() as db:
                    db.execute('UPDATE requests SET state=?,detail=? WHERE id=? AND topic_id=?', (state, detail, request['id'], topic['id']))
            results.append({'business_id': topic['business_id'], 'topic_id': topic['id'], 'name': topic['name'], 'state': state, 'detail': detail})
    return json.dumps(results, ensure_ascii=False)


def request_run(store, request_id):
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
        raise ValueError('执行请求 ID 无效')
    with store.workspace.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute("INSERT OR IGNORE INTO requests(id,topic_id,kind) VALUES (?,?,'manual')", (request_id, store.scope['id']))
