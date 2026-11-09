"""Content categories page their actual members and omit heavyweight evidence by default."""
import json

import pytest

from plugins.operations.content_library import listing, detail
from plugins.operations.store import Store


def draft(store, identity, **fields):
    return store.put('content', {'title': identity, 'body': '完整正文' * 40, 'asset_ids': [], 'source_ids': [], **fields}, identity)


def test_filtering_precedes_paging_and_compact_lists_exclude_full_evidence(tmp_path):
    store = Store(tmp_path / 'library.db')
    draft(store, 'scheduled', analysis_context={'large': '原始依据' * 20000})
    store.put('content_release', {'state': 'scheduled', 'revision': 1, 'publish_at': '2027-01-01T00:00:00+00:00'}, 'content-release:scheduled')
    for index in range(101):
        draft(store, f'draft-{index}', analysis_context={'large': '原始依据' * 20000})
    store.put('source', {'text': '来源全文' * 50000}, 'source')
    result = listing(store, filter='pending', compact=True)
    assert [row['id'] for row in result['content']] == ['scheduled']
    assert result['next'] is None and result['counts']['drafts'] == 101
    assert len(json.dumps(result, ensure_ascii=False)) < 3000
    assert 'source' not in result and 'analysis_context' not in result['content'][0]
    page = listing(store, filter='drafts', compact=True)
    next_page = listing(store, before=int(page['next']), filter='drafts', compact=True)
    assert len(page['content']) == 24
    assert not {row['id'] for row in page['content']} & {row['id'] for row in next_page['content']}
    assert len(detail(store, 'scheduled')['content']['body']) > 140


@pytest.mark.parametrize(('state', 'filter'), [('failed', 'failed'), ('cancelled', 'failed'), ('submitted', 'needs_attention'), ('executing', 'in_progress'), ('published', 'published')])
def test_acted_manuscripts_belong_to_publication_records_not_review_queue(tmp_path, state, filter):
    store = Store(tmp_path / 'library.db')
    draft(store, 'content')
    with store.connection() as db:
        db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?)', ('action', '2026-11-08', 0, 'publish', 'target', state,
                   json.dumps({'content': {'id': 'content', 'title': '原稿', 'body': '正文', 'asset_ids': []}}), '{}', '2026-11-08'))
    assert listing(store, filter='drafts', compact=True)['content'] == []
    result = listing(store, filter='published', status=filter, compact=True)
    assert [row['id'] for row in result['actions']] == ['action']
    assert result['actions'][0]['publication_state'] == state
    assert detail(store, 'action', publication=True)['action']['id'] == 'action'


def test_direct_version_link_can_inspect_an_acted_parent_without_adding_it_to_review_queue(tmp_path):
    store = Store(tmp_path / 'library.db')
    draft(store, 'parent')
    with store.connection() as db:
        db.execute("INSERT INTO actions VALUES ('old','2026-11-08',0,'publish','target','published',?,'{}','2026-11-08')", (json.dumps({'content': {'id': 'parent'}}),))
    assert not listing(store, filter='drafts', compact=True)['content']
    assert listing(store, filter='drafts', record='parent', compact=True)['content'][0]['publication_action_id'] == 'old'
