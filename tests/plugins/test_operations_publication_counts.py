"""Platform publication is a distinct fact from exact approval-image verification."""
import json
from plugins.operations.store import Store
from plugins.operations.overview import overview
from plugins.operations.policy import local_day


def test_published_platform_receipt_counts_even_when_cdn_image_check_is_pending(tmp_path):
    store = Store(tmp_path / 'topic.db')
    day = local_day(store.policy()[1])
    with store.connection() as db:
        for identity, platform, content in [('visible', 'published', 'incomplete'), ('review', 'reviewing', 'matched'), ('unknown', 'unknown', 'matched')]:
            result = {'evidence': '笔记管理核对', 'note_id': identity, 'publication': {'execution': 'verified', 'platform': platform, 'content': content}}
            db.execute('INSERT INTO actions VALUES (?,?,0,?,?,?,?,?,?)', (identity, day, 'publish', identity, 'submitted', json.dumps({'content': {'title': identity}}), json.dumps(result), day + 'T01:00:00+00:00'))
    result = overview(store)
    assert result['counts']['published'] == 1
    assert [row['id'] for row in result['publications']] == ['visible']
    assert result['publications'][0]['content_state'] == 'incomplete'
    with store.connection() as db:
        assert db.execute("SELECT state FROM actions WHERE id='visible'").fetchone()[0] == 'submitted'

    from plugins.operations.content_library import listing
    assert [row['id'] for row in listing(store, filter='published', status='published')['actions']] == ['visible']
    from plugins.operations.publication_status import platform_published, complete
    with store.connection() as db:
        rows = [dict(row) for row in db.execute('SELECT * FROM actions')]
    assert sum(platform_published(row) for row in rows) == 1
    assert sum(complete(row) for row in rows) == 0
