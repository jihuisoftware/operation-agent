"""Read-only schedule waiting reasons; never consume approval or start a publication."""
from datetime import UTC, datetime
import json

from .store_reads import worker_status

DETAIL = '发布时间已到，正在等待桌面网页执行器连接；尚未提交。'


def project(db, release, *, now=None, worker=None):
    if not release or release.get('state') != 'scheduled':
        return release
    now = now or datetime.now(UTC)
    if datetime.fromisoformat(release['publish_at']) > now:
        return release
    worker = worker if worker is not None else worker_status(db)
    if worker['online']:
        return release
    return {**release, 'waiting': {'code': 'WORKER_OFFLINE', 'detail': DETAIL,
                                  'last_seen': worker['last_seen']}}


def annotate(db, rows):
    worker = worker_status(db)
    now = datetime.now(UTC)
    for row in rows:
        if not row.get('publication_state') and row.get('release'):
            row['release'] = project(db, row['release'], now=now, worker=worker)


def pending_detail(store, now):
    with store.connection() as db:
        row = db.execute("SELECT r.data FROM objects r WHERE r.kind='content_release' "
                         "AND json_extract(r.data,'$.state')='scheduled' "
                         "AND NOT EXISTS (SELECT 1 FROM actions a WHERE a.kind='publish' "
                         "AND json_extract(a.data,'$.content.id')=json_extract(r.data,'$.content_id')) "
                         "ORDER BY json_extract(r.data,'$.publish_at') LIMIT 1").fetchone()
        release = project(db, json.loads(row[0]), now=now) if row else None
    return (release or {}).get('waiting', {}).get('detail')
