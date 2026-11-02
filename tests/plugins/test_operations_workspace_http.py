"""Scope validation is enforced on reads, exports and writes by the private API."""
from starlette.testclient import TestClient


def test_scoped_http_requires_an_unambiguous_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('{}')
    from hermes_cli import web_server
    with TestClient(web_server.app) as client:
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        base = '/api/plugins/operations'
        first = client.post(base + '/workspaces', json={'action': 'create', 'name': '甲'}).json()
        second = client.post(base + '/workspaces', json={'action': 'create', 'name': '乙'}).json()
        for scope in (first, second):
            assert client.get(base + '/policy', params=scope).status_code == 200
        assert client.get(base + '/policy', params={'business_id': first['business_id'], 'topic_id': second['topic_id']}).status_code == 404
        assert client.get(base + '/policy', params={'topic_id': first['topic_id']}).status_code == 404
        assert client.get(base + '/policy').status_code == 404
        from plugins.operations.workspaces import Workspaces
        directory = Workspaces()
        directory.store(first['business_id'], first['topic_id']).put('source', {'title': '甲资料', 'text': '公开正文', 'url': 'https://example.org/a'}, 'only-first')
        assert not client.get(base + '/sources', params=second).json()['items']
        assert client.post(base + '/workspaces/reference', params=second, json={'source_topic_id': first['topic_id'], 'source_id': 'only-first'}).status_code == 400
        assert client.get(base + '/assets/only-first', params=second).status_code == 404
        archived = client.post(base + '/workspaces', json={'action': 'archive', 'kind': 'topics', 'id': first['topic_id']})
        assert archived.status_code == 200, archived.text
        assert client.get(base + '/sources', params=first).status_code == 200
        assert client.put(base + '/policy', params=first, json={'version': 0, 'policy': {}}).status_code == 409


def test_outdated_directory_requires_explicit_development_reset(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('{}')
    from plugins.operations.workspaces import Workspaces
    directory = Workspaces()
    with directory.connection() as db:
        db.execute('PRAGMA user_version=0')
    from hermes_cli import web_server
    with TestClient(web_server.app) as client:
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        response = client.get('/api/plugins/operations/workspaces')
        assert response.status_code == 409
        assert '清理运营数据' in response.json()['detail']
