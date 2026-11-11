"""Working drafts remain isolated from immutable publication and retain evidence."""
import uuid

import pytest

from plugins.operations import writing_drafts as drafts, writing_submission as submission
from plugins.operations.writing_document import from_plain, validate, project
from plugins.operations.store import Store
from tests.plugins import test_operations_content_review as support

cover_manuscript = support.manuscript


def request(**values):
    return {'request_id': uuid.uuid4().hex, **values}


def test_long_incomplete_draft_cas_and_idempotency_survive_reopening(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    created = drafts.create(store, request())
    data = drafts.detail(store, created['id'])
    body = request(**drafts.fields(data), expected_revision=1)
    body['document'] = from_plain('长文章' * 10000)
    saved = drafts.save(store, data['id'], body)
    assert saved['revision'] == 2
    assert drafts.save(Store(), data['id'], body) == saved
    with pytest.raises(drafts.DraftConflict):
        drafts.save(store, data['id'], request(**drafts.fields(data), expected_revision=1))
    assert len(project(drafts.detail(store, data['id'])['document'])['body']) == 30000
    assert not store.objects('content') and not store.objects('action')
    with pytest.raises(ValueError):
        submission.submit(store, data['id'], request(expected_revision=2, version=0))


def test_original_submit_is_idempotent_and_reuses_content_after_working_draft_save(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    created = drafts.create(store, request())
    data = drafts.detail(store, created['id'])
    fields = {**drafts.fields(data), 'title': '原创实践', 'document': from_plain('今天分享我的实践经验。'), 'original': True}
    drafts.save(store, data['id'], request(**fields, expected_revision=1))
    body = request(expected_revision=2, version=0)
    first = submission.submit(store, data['id'], body)
    second = submission.submit(store, data['id'], request(expected_revision=2, version=0))
    assert first['content_id'] == second['content_id']
    content = store.objects('content')[0]
    assert content['editor_document'] == fields['document'] and content['source_ids'] == []
    assert content['authorship']['declared'] and content['state'] == 'pending_review'
    drafts.save(store, data['id'], request(**{**fields, 'title': '修改标题'}, expected_revision=2))
    assert store.objects('content')[0] == content
    assert not store.objects('content_release')
    changed = submission.submit(store, data['id'], request(expected_revision=3, version=0))
    child = next(row for row in store.objects('content') if row['id'] == changed['content_id'])
    assert child['revision_root_id'] == content['id']
    assert changed['content_id'] == first['content_id']
    assert len(store.objects('content')) == 1
    assert child['title'] == '修改标题'
    assert store.objects('content_edit_history')[0]['content']['title'] == content['title']


def test_derived_draft_cannot_erase_provenance(cover_manuscript):
    store, _, _, parent = cover_manuscript
    created = drafts.create(store, request(from_content=parent['id']))
    data = drafts.detail(store, created['id'])
    assert data['source_ids'] == parent['source_ids']
    with pytest.raises(ValueError, match='原稿依据'):
        drafts.save(store, data['id'], request(**{**drafts.fields(data), 'original': True, 'source_ids': []}, expected_revision=1))
    result = submission.submit(store, data['id'], request(expected_revision=1, version=1))
    child = next(row for row in store.objects('content') if row['id'] == result['content_id'])
    assert child['analysis_context'] == parent['analysis_context']
    assert child['id'] == parent['id']
    assert len(store.objects('content')) == 1


def test_projection_keeps_literal_legacy_text_and_orders_images():
    document = from_plain('# 标题\n**不是 Markdown**\n<script>原文</script>', ['a', 'b', 'a'])
    result = project(validate(document), 'b')
    assert result['body'] == '# 标题\n**不是 Markdown**\n<script>原文</script>'
    assert result['asset_ids'] == ['b', 'a']
    document['content'].append({'type': 'uploadPlaceholder', 'attrs': {'name': '外链图', 'id': 'x', 'state': 'external'}})
    assert project(validate(document))['pending_images'] == ['外链图']
    with pytest.raises(ValueError):
        validate({'type': 'doc', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': '链接', 'marks': [{'type': 'link', 'attrs': {'href': 'javascript:alert(1)'}}]}]}]})


def test_shared_projection_fixture():
    import json
    from pathlib import Path
    fixture = json.loads((Path(__file__).parents[2] / 'apps/desktop/src/plugins/operations/writing/fixtures/document.json').read_text())
    projected = project(validate(fixture['document']), fixture['cover'])
    assert {key: projected[key] for key in fixture['expected']} == fixture['expected']


def test_private_draft_api_scope_and_summary_payload(cover_manuscript):
    from starlette.testclient import TestClient
    from hermes_cli import web_server
    store, _, _, parent = cover_manuscript
    scope = {'business_id': store.scope['business_id'], 'topic_id': store.scope['id']}
    path = '/api/plugins/operations/content/writing-drafts'
    with TestClient(web_server.app) as client:
        assert client.get(path, params=scope).status_code == 401
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        created = client.post(path, params=scope, json=request(from_content=parent['id']))
        assert created.status_code == 200, created.text
        identity = created.json()['id']
        detail = client.get(path + '/' + identity, params=scope)
        assert detail.status_code == 200 and detail.json()['source_ids'] == parent['source_ids']
        listing = client.get(path, params=scope).json()
        assert listing['items'][0]['id'] == identity and 'document' not in listing['items'][0]
        invalid = client.get(path + '/' + identity, params={**scope, 'topic_id': 'unrelated'})
        assert invalid.status_code in (400, 403, 404)


def test_concurrent_submit_different_requests_share_one_revision(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    identity = drafts.create(store, request())['id']
    data = drafts.detail(store, identity)
    fields = {**drafts.fields(data), 'title': '并发提交', 'document': from_plain('同一修订只生成一份正式稿。'), 'original': True}
    drafts.save(store, identity, request(**fields, expected_revision=1))
    # Pre-generate cover assets to isolate the submission race from artwork creation.
    ready = submission.build(store, drafts.detail(store, identity), *store.policy())
    gate = Barrier(2)
    def build(*_):
        gate.wait(timeout=10)
        return dict(ready)
    monkeypatch.setattr(submission, 'build', build)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submission.submit, store, identity, request(expected_revision=2, version=0)) for _ in range(2)]
        results = [future.result(timeout=15) for future in futures]
    assert results[0]['content_id'] == results[1]['content_id']
    assert len(store.objects('content')) == 1


def test_pending_image_and_revoked_asset_block_submit_but_not_saving(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    identity = drafts.create(store, request())['id']
    data = drafts.detail(store, identity)
    document = from_plain('正文完整')
    document['content'].append({'type': 'uploadPlaceholder', 'attrs': {'id': 'upload', 'name': '上传失败', 'state': 'failed'}})
    fields = {**drafts.fields(data), 'title': '检查图片', 'document': document, 'original': True}
    drafts.save(store, identity, request(**fields, expected_revision=1))
    with pytest.raises(ValueError, match='图片未上传'):
        submission.submit(store, identity, request(expected_revision=2, version=0))
    fields['document'] = from_plain('正文完整', ['revoked'])
    drafts.save(store, identity, request(**fields, expected_revision=2))
    with pytest.raises(ValueError):
        submission.submit(store, identity, request(expected_revision=3, version=0))
    assert not store.objects('content')
