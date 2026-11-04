"""Budget settings use authenticated profile/topic routing and reject stale saves."""
from starlette.testclient import TestClient


def test_budget_http_persists_shared_settings_and_rejects_foreign_scope(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('{}')
    from hermes_cli import web_server
    with TestClient(web_server.app) as client:
        base = '/api/plugins/operations'
        assert client.get(base + '/model-budget').status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        scope = client.post(base + '/workspaces', json={'action': 'create', 'name': '预算主题'}).json()
        response = client.get(base + '/model-budget', params=scope)
        assert response.status_code == 200, response.text
        before = response.json()
        body = {'version': before['version'], 'config': {'mode': 'tokens', 'calls': 200, 'tokens': 50000}}
        saved = client.put(base + '/model-budget', params=scope, json=body)
        assert saved.status_code == 200, saved.text
        assert client.get(base + '/model-budget', params=scope).json()['config'] == body['config']
        assert client.put(base + '/model-budget', params=scope, json=body).status_code == 400
        assert client.get(base + '/model-budget', params={**scope, 'topic_id': 'foreign'}).status_code == 404
        invalid = {**body, 'version': saved.json()['version'], 'config': {**body['config'], 'tokens': -1}}
        assert client.put(base + '/model-budget', params=scope, json=invalid).status_code == 400
        policy = client.get(base + '/policy', params=scope).json()
        policy['policy'].update(model_budget_mode='tokens', model_tokens=20000, model_calls=200)
        assert client.put(base + '/policy', params=scope, json=policy).status_code == 200
        reloaded = client.get(base + '/policy', params=scope).json()['policy']
        assert (reloaded['model_budget_mode'], reloaded['model_tokens'], reloaded['model_calls']) == ('tokens', 20000, 200)
        assert client.get(base + '/model-budget', params=scope).json()['config'] == body['config']
