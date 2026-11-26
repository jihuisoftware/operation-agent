"""Old topic indexes retain revisit state and accept both collection write paths."""
import json
import sqlite3

import pytest

from plugins.operations.collection_revisit import save_observation, snapshot
from plugins.operations.store import Store


@pytest.mark.parametrize("existing_author", [False, True], ids=['nine-columns', 'partial-upgrade'])
def test_open_old_index_and_resume_collection(tmp_path, existing_author):
    path = tmp_path / 'topic.db'
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE collection_urls (
            topic TEXT NOT NULL, url TEXT NOT NULL, last_day TEXT NOT NULL, next_day TEXT NOT NULL,
            digest TEXT NOT NULL, unchanged INTEGER NOT NULL, source_id TEXT NOT NULL, feed_updated TEXT,
            origins TEXT NOT NULL, PRIMARY KEY(topic,url))""")
        db.execute("INSERT INTO collection_urls VALUES (?,?,?,?,?,?,?,?,?)",
                   ('新闻', 'https://example.org/old', '2026-11-20', '2026-12-04', 'old-hash', 3, 'old', None, '[]'))
        if existing_author:
            db.execute('ALTER TABLE collection_urls ADD COLUMN author TEXT')
            db.execute("UPDATE collection_urls SET author='原有署名'")
        db.execute('CREATE TABLE objects(id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL, created TEXT NOT NULL)')
        for name in ('old', 'bootstrap'):
            source = {'scope_topic': '新闻', 'day': '2026-11-20', 'url': 'https://example.org/' + name,
                      'text': '有效正文', 'title': '旧标题', 'published_at': '2026-11-17', 'author': '资料署名'}
            db.execute("INSERT INTO objects VALUES (?, 'source', ?, '2026-11-20')", (name, json.dumps(source)))

    store = Store(path)
    history, _, _ = snapshot(store, '新闻', '2026-11-26')
    old = history['https://example.org/old']
    assert (old['digest'], old['unchanged'], old['next_day']) == ('old-hash', 3, '2026-12-04')
    assert old['title'] == '旧标题' and old['author'] == ('原有署名' if existing_author else '资料署名')
    assert history['https://example.org/bootstrap']['published_at'] == '2026-11-17'

    record = {**source, 'url': old['url'], 'day': '2026-11-26', 'fingerprint': 'new-hash',
              'origins': [], 'title': '新版', 'author': '新署名', 'published_at': '2026-11-25'}
    with store.connection() as db:
        save_observation(db, record, 'new', 0)
    history, _, _ = snapshot(Store(path), '新闻', '2026-11-26')
    updated = history[old['url']]
    assert (updated['source_id'], updated['title'], updated['author'], updated['published_at']) == (
        'new', '新版', '新署名', '2026-11-25')
