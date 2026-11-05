"""Human approval authorizes exactly one version; debug can review and publish once."""
from copy import deepcopy
from datetime import datetime, UTC, timedelta
from io import BytesIO
import json

from PIL import Image
import pytest

from plugins.operations import content, content_release, workflow
from plugins.operations.content_runs import generate
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store, encoded
from tests.plugins.operations_support import prepare_materials


@pytest.fixture
def manuscript(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('development:\n  operations_debug: true\n')
    store = Store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='步行路线', goal='可核对的路线指南', account_id='me')
    policy['modules'].update(content=True, topics=True, organize=True, publish=True)
    policy['allowed']['publish'] = False
    store.configure(policy, 0)
    day = local_day(policy)
    store.put('source', {'day': day, 'scope_topic': policy['topic'], 'text': '路线开放时间为九点',
                        'state': 'read', 'title': '路线信息', 'url': 'https://example.org/walk'}, 'source')
    prepare_materials(store, policy, day, monkeypatch)
    from plugins.operations import topics
    monkeypatch.setattr(topics, 'generate', lambda *_: {'topics': [{'title': '步行路线', 'source_ids': ['source']}]})
    monkeypatch.setattr(content, 'generate', lambda *_: {'title': '步行路线', 'body': '路线开放时间为九点。', 'source_ids': ['source'], 'asset_ids': []})
    monkeypatch.setattr(content, 'check_content', lambda *_a, **_kw: {'pass': True, 'reason': '来源可核对'})
    request = {'version': 1, 'request_id': 'complete'}
    result = generate(store, request)
    assert result['state'] == 'completed', result
    assert generate(store, request) == result
    return store, policy, day, store.objects('content')[0]


def approve(store, draft):
    due = datetime.now(UTC) + timedelta(minutes=5)
    body = {'version': 1, 'content_revision': content_release.fingerprint(draft), 'expected_revision': 0, 'publish_at': due.isoformat()}
    return due, body, content_release.review(store, draft['id'], body)


def desktop(store, monkeypatch, *, state='published'):
    original = Store.command
    seen = []
    def receive(self, identity):
        command = self.claim('test-desktop')
        assert command and command['id'] == identity
        seen.append(command)
        self.acknowledge(identity, 'test-desktop', {'state': state, 'evidence': '模拟平台核对回执'})
        return original(self, identity)
    monkeypatch.setattr(Store, 'command', receive)
    store.claim('test-desktop', busy=True)
    return seen


def test_complete_cover_waits_for_review_then_scheduled_tick_publishes_exactly_once(manuscript, monkeypatch):
    store, policy, day, draft = manuscript
    from plugins.operations.publication_snapshot import asset_bytes
    raw = asset_bytes(store.objects('asset')[0])
    assert Image.open(BytesIO(raw)).size == (1080, 1440)
    assert draft['state'] == 'pending_review' and draft['ready']
    from plugins.operations.outcomes import StageSkipped
    with pytest.raises(StageSkipped, match='人工审核'):
        workflow.publish(store, policy, day, 1)
    due, body, approval = approve(store, draft)
    with pytest.raises(ValueError, match='排期已变化'):
        content_release.review(store, draft['id'], body)
    seen = desktop(store, monkeypatch)
    from plugins.operations.runtime import tick
    tick(store, due - timedelta(seconds=1), scheduled=True)
    assert not seen
    # A newly opened store simulates loading the durable schedule after a restart.
    reopened = Store(store.path, workspace=store.workspace, scope=store.scope)
    tick(reopened, due + timedelta(seconds=1), scheduled=True)
    assert len(seen) == 1
    assert seen[0]['payload']['content']['id'] == draft['id']
    assert seen[0]['payload']['human_review'] == approval['revision']
    assert not store.policy()[1]['allowed']['publish']
    tick(store, due + timedelta(seconds=2), scheduled=True)
    assert len(seen) == 1


@pytest.mark.parametrize('change', ['cancel', 'content', 'source', 'rules'])
def test_changed_or_cancelled_approval_never_submits(manuscript, monkeypatch, change):
    store, policy, _, draft = manuscript
    due, _, approval = approve(store, draft)
    if change == 'cancel':
        content_release.cancel(store, draft['id'], approval['revision'])
    elif change == 'rules':
        store.configure({**policy, 'goal': '新的目标'}, 1)
    else:
        kind, identity = ('content', draft['id']) if change == 'content' else ('source', 'source')
        with store.connection() as db:
            row = json.loads(db.execute('SELECT data FROM objects WHERE kind=? AND id=?', (kind, identity)).fetchone()[0])
            row['body' if change == 'content' else 'text'] = '修改后的内容'
            db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(row), identity))
    seen = desktop(store, monkeypatch)
    from plugins.operations.runtime import tick
    tick(store, due + timedelta(seconds=1), scheduled=True)
    assert not seen


@pytest.mark.parametrize('mode', ['quick', 'normal'])
def test_debug_reviews_and_publishes_without_granting_normal_automation(manuscript, monkeypatch, mode):
    store, _, _, draft = manuscript
    seen = desktop(store, monkeypatch)
    from devtools.operations_debug import execute
    body = {'task': 'publish', 'version': 1, 'mode': mode, 'request_id': 'debug-publish'}
    if mode == 'quick':
        body['external_actions'] = 'execute_once'
    result = execute(body)
    assert result['state'] == 'completed', result
    assert len(seen) == 1 and seen[0]['payload']['content']['id'] == draft['id']
    assert execute(body) == result and len(seen) == 1
    assert not store.objects('content_release') and not store.policy()[1]['allowed']['publish']


def test_review_http_requires_authentication_and_owning_topic(manuscript, monkeypatch):
    from starlette.testclient import TestClient
    from hermes_cli import web_server
    from plugins.operations import runtime
    store, _, _, draft = manuscript
    monkeypatch.setattr(runtime, 'ensure_schedule', lambda *_: 'schedule')
    scope = {'business_id': store.scope['business_id'], 'topic_id': store.scope['id']}
    body = {'version': 1, 'content_revision': content_release.fingerprint(draft), 'expected_revision': 0,
            'publish_at': (datetime.now(UTC) + timedelta(hours=1)).isoformat()}
    with TestClient(web_server.app) as client:
        path = f"/api/plugins/operations/content/{draft['id']}/approve"
        assert client.post(path, params=scope, json=body).status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        assert client.post(path, params={**scope, 'topic_id': 'foreign'}, json=body).status_code == 404
        result = client.post(path, params=scope, json=body)
        assert result.status_code == 200, result.text
        assert result.json()['state'] == 'scheduled'
        assert client.post(path, params=scope, json=body).status_code == 400


def test_generated_cover_does_not_invalidate_pending_draft_reuse(manuscript, monkeypatch):
    store, policy, day, draft = manuscript
    draft.update(review_pending=True, ready=False)
    with store.connection() as db:
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(draft), draft['id']))
    monkeypatch.setattr(content, 'generate', lambda *_: pytest.fail('已保存的草稿不应因新封面重新生成正文'))
    result = content.produce_content(store, policy, day, 1)
    assert result['content_id'] == draft['id']
    assert len(store.objects('content')) == 1


def test_unknown_scheduled_result_requires_manual_reconciliation_before_retry(manuscript, monkeypatch):
    from plugins.operations import service
    from plugins.operations.runtime import tick
    store, _, _, draft = manuscript
    due, _, _ = approve(store, draft)
    seen = desktop(store, monkeypatch, state='unknown')
    tick(store, due + timedelta(seconds=1), scheduled=True)
    assert len(seen) == 1
    identity = store.snapshot()['actions'][0]['id']
    with pytest.raises(ValueError, match='先核对'):
        service.retry_action(store, identity)
    service.resolve_action(store, identity, 'confirmed_not_published', '人工核对平台笔记列表，确认此稿没有发布')
    command = service.retry_action(store, identity)
    assert store.claim('test-desktop')['id'] == command
    assert len(store.snapshot()['actions']) == 1
