"""Explicit topic regeneration preserves profile/workspace ownership and request idempotency."""
from copy import deepcopy

from starlette.testclient import TestClient

from plugins.operations import topics
from plugins.operations.model_budget import quota_exempt
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.workspaces import Workspaces
from tests.plugins.operations_support import prepare_materials


def test_generation_http_is_scoped_idempotent_and_not_debug_exempt(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('{}')
    store = Workspaces().store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='接口选题', goal='生成有来源的选题')
    policy['modules'].update(topics=True, organize=True)
    store.configure(policy, 0)
    day = local_day(policy)
    store.put('source', {'day': day, 'scope_topic': policy['topic'], 'title': '原文', 'text': '完整且可核对的来源正文',
                        'url': 'https://example.org/article', 'state': 'read'}, 'source')
    prepare_materials(store, policy, day, monkeypatch)
    calls = []
    def generate(active, *_):
        assert not quota_exempt(active)
        calls.append(active.scope['id'])
        return {'topics': [{'title': '具体题目', 'source_ids': ['source']}]}
    monkeypatch.setattr(topics, 'generate', generate)
    from hermes_cli import web_server
    with TestClient(web_server.app) as client:
        path = '/api/plugins/operations/topics/generate'
        body = {'version': 1, 'request_id': 'regenerate-one', 'force': True}
        scope = {'business_id': store.scope['business_id'], 'topic_id': store.scope['id']}
        assert client.post(path, json=body, params=scope).status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        response = client.post(path, json=body, params=scope)
        assert response.status_code == 200 and response.json()['state'] == 'completed', response.text
        assert client.post(path, json=body, params=scope).json() == response.json()
        assert calls == [store.scope['id']]
        assert client.post(path, json={**body, 'force': False}, params=scope).status_code == 400
        assert client.post(path, json=body, params={**scope, 'topic_id': 'foreign'}).status_code == 404
        reused = client.post(path, json={**body, 'request_id': 'reuse-two', 'force': False}, params=scope)
        assert reused.status_code == 200 and '复用' in reused.json()['detail']
        assert len(calls) == 1
