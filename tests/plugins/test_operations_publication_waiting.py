"""Overdue schedules explain an offline executor without consuming the approved attempt."""
from datetime import UTC, datetime, timedelta
import json
import time


from plugins.operations import content_library, publication_plan
from plugins.operations.store import encoded
from tests.plugins import test_operations_content_review as support

manuscript = support.manuscript


def overdue(store, draft):
    support.approve(store, draft)
    with store.connection() as db:
        release = support.content_release.load(db, draft['id'])
        release['publish_at'] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        db.execute('UPDATE objects SET data=? WHERE id=?',
                   (encoded(release), 'content-release:' + draft['id']))
    return release


def test_offline_due_schedule_is_visible_and_publishes_once_after_reconnect(manuscript, monkeypatch):
    store, _, _, draft = manuscript
    release = overdue(store, draft)
    seen_at = time.time() - 60
    with store.connection() as db:
        db.execute('DELETE FROM workers')
        db.execute('INSERT INTO workers VALUES (?,?)', ('old-desktop', seen_at))
    assert not publication_plan.publish_due(store, datetime.now(UTC))
    for compact in (True, False):
        row = content_library.listing(store, filter='pending', compact=compact)['content'][0]
        assert row['release']['state'] == 'scheduled'
        assert row['release']['waiting']['code'] == 'WORKER_OFFLINE'
        assert row['release']['waiting']['last_seen'] == datetime.fromtimestamp(seen_at, UTC).isoformat()
    details = content_library.detail(store, draft['id'])['content']
    assert details['release']['waiting']['code'] == 'WORKER_OFFLINE'
    with store.connection() as db:
        saved = json.loads(db.execute('SELECT data FROM objects WHERE id=?', ('content-release:' + draft['id'],)).fetchone()[0])
        assert saved == release
        assert db.execute('SELECT count(*) FROM actions').fetchone()[0] == 0
        assert not db.execute("SELECT 1 FROM runs WHERE slot LIKE 'content-release:%'").fetchone()
    calls = support.desktop(store, monkeypatch)
    assert content_library.listing(store, filter='pending', compact=True)['content'][0]['release'].get('waiting') is None
    assert publication_plan.publish_due(store, datetime.now(UTC))
    assert not publication_plan.publish_due(store, datetime.now(UTC))
    assert len(calls) == 1


def test_tick_reports_offline_wait_without_claiming_success_or_changing_a_future_schedule(manuscript, monkeypatch):
    from plugins.operations import runtime, workspace_upcoming
    store, _, _, draft = manuscript
    monkeypatch.setattr(workspace_upcoming, 'queue_due', lambda *_: {})
    _, _, release = support.approve(store, draft)
    with store.connection() as db:
        db.execute('DELETE FROM workers')
    row = content_library.listing(store, filter='pending', compact=True)['content'][0]
    assert row['release'].get('waiting') is None
    result = runtime.tick(store, datetime.fromisoformat(release['publish_at']) + timedelta(seconds=1), scheduled=True)
    assert '等待桌面网页执行器连接' in result
    with store.connection() as db:
        assert db.execute('SELECT count(*) FROM actions').fetchone()[0] == 0
