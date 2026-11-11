"""Cover/text edits retain server-owned evidence and never silently replace a schedule."""
import pytest
from plugins.operations.store import encoded

from plugins.operations import content_release
from plugins.operations.content_versions import create
from tests.plugins import test_operations_content_review as support

_base_manuscript = support.manuscript


@pytest.fixture
def version_case(_base_manuscript):
    store, policy, day, draft = _base_manuscript
    from plugins.operations.analysis_config import settings, window
    config = settings(store)
    draft["analysis_context"] = {"scope_topic": policy["topic"], "window": window(config["config"], day),
                                 "config_version": config["version"], "datasets": [], "findings": []}
    with store.connection() as db:
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(draft), draft['id']))
    return store, policy, day, draft


def request(draft, **extra):
    return {'request_id': 'edit', 'version': 1, 'content_revision': content_release.fingerprint(draft), **extra}


def test_edit_in_place_inherits_evidence_is_idempotent_and_invalidates_schedule(version_case):
    store, _, _, draft = version_case
    _, _, release = support.approve(store, draft)
    with store.connection() as db:
        release = content_release.load(db, draft['id'])
    result = create(store, draft['id'], request(draft, title='新标题'))
    child = content_release.manuscript(store, result['id'])
    assert result == create(store, draft['id'], request(draft, title='新标题'))
    for field in ('analysis_context', 'organization_ids', 'organized_evidence'):
        assert child[field] == draft[field]
    assert child['id'] == draft['id'] and child['manual_revision']
    assert len(store.objects('content')) == 1
    assert store.objects('content_edit_history')[0]['content']['title'] == draft['title']
    assert child['asset_ids'][0] != draft['asset_ids'][0]
    assert child['state'] == 'pending_review'
    with store.connection() as db:
        assert content_release.load(db, draft['id'])['state'] == 'cancelled'
        assert content_release.load(db, draft['id'])['revision'] == release['revision'] + 1
    assert result['original_schedule_retained'] is False
    with pytest.raises(ValueError, match='同一保存请求'):
        create(store, draft['id'], request(draft, title='其他标题'))


def test_edit_rejects_stale_content_and_cancels_schedule_atomically(version_case):
    store, _, _, draft = version_case
    _, _, release = support.approve(store, draft)
    body = request(draft, cancel_original_schedule=True, expected_release_revision=release['revision'])
    result = create(store, draft['id'], body)
    with store.connection() as db:
        assert content_release.load(db, draft['id'])['state'] == 'cancelled'
    assert not result['original_schedule_retained']
    assert create(store, draft['id'], body) == result
    with pytest.raises(ValueError, match='原稿或规则'):
        create(store, draft['id'], {**body, 'request_id': 'stale'})


def test_edit_rejects_forged_or_changed_evidence_and_stale_parent(version_case):
    store, _, _, draft = version_case
    with pytest.raises(ValueError, match='服务端继承'):
        create(store, draft['id'], request(draft, analysis_context={}))
    with pytest.raises(ValueError, match='原稿或规则'):
        create(store, draft['id'], {**request(draft), 'content_revision': 'stale'})
    from plugins.operations.analysis_config import DEFAULT
    store.put('analysis_config', {'version': draft['analysis_context']['config_version'] + 1, 'config': DEFAULT}, 'analysis-config')
    with pytest.raises(ValueError, match='分析|权限|范围'):
        create(store, draft['id'], request(draft))


def test_content_endpoints_bind_profile_scope_and_match_the_editor_contract(version_case):
    from starlette.testclient import TestClient
    from hermes_cli import web_server
    store, _, _, draft = version_case
    base = '/api/plugins/operations'
    scope = {'business_id': store.scope['business_id'], 'topic_id': store.scope['id']}
    with TestClient(web_server.app) as client:
        assert client.get(f"{base}/content/{draft['id']}/details", params=scope).status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        listing = client.get(base + '/library/content', params={**scope, 'filter': 'drafts', 'compact': 'true'})
        assert listing.status_code == 200 and listing.json()['compact'] is True
        assert 'analysis_context' not in listing.json()['content'][0]
        detail = client.get(f"{base}/content/{draft['id']}/details", params=scope).json()
        assert detail['content']['content_revision'] == content_release.fingerprint(draft)
        assert 'text' not in detail['sources'][0]
        created = client.post(f"{base}/content/{draft['id']}/versions", params=scope, json=request(draft, title='接口编辑版本'))
        assert created.status_code == 200, created.text
        saved = content_release.manuscript(store, created.json()['id'])
        assert saved['analysis_context'] == draft['analysis_context']
        assert client.get(f"{base}/content/{draft['id']}/details", params={**scope, 'topic_id': 'foreign'}).status_code == 404


def test_edit_keeps_published_snapshot_and_returns_original_to_review(version_case, monkeypatch):
    from datetime import timedelta
    from plugins.operations.runtime import tick
    from plugins.operations.content_library import listing, detail
    store, _, _, draft = version_case
    due, _, _ = support.approve(store, draft)
    support.desktop(store, monkeypatch)
    tick(store, due + timedelta(seconds=1), scheduled=True)
    with store.connection() as db:
        action = dict(db.execute("SELECT * FROM actions WHERE kind='publish'").fetchone())
    result = create(store, draft['id'], request(draft, title='更新后的路线'))
    assert result['id'] == draft['id']
    assert [row['id'] for row in listing(store, filter='drafts', compact=True)['content']] == [draft['id']]
    assert detail(store, draft['id'])['content']['publication_state'] is None
    historical = detail(store, action['id'], publication=True)
    assert historical['content']['title'] == draft['title']
    with store.connection() as db:
        assert dict(db.execute('SELECT * FROM actions WHERE id=?', (action['id'],)).fetchone()) == action
    current = content_release.manuscript(store, draft['id'])
    with pytest.raises(ValueError, match='原稿或规则'):
        create(store, draft['id'], {**request(draft, title='过期编辑'), 'request_id': 'stale-window'})
    assert current['title'] == '更新后的路线'
