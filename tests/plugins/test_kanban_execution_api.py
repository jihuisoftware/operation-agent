"""The bundled Desktop router is private and manual mutations never dispatch workers."""
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def private_client(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setenv('HERMES_KANBAN_HOME', str(tmp_path))
    from hermes_cli import web_server as ws, web_server_dashboard as dashboard
    routes = list(ws.app.router.routes)
    ws._dashboard_plugins_cache = None
    dashboard._mount_plugin_api_routes()
    monkeypatch.setattr('hermes_cli.kanban._check_dispatcher_presence', lambda **kw: (False, '测试后台未运行'))
    client = TestClient(ws.app)
    try:
        yield client, {ws._SESSION_HEADER_NAME: ws._SESSION_TOKEN}
    finally:
        ws.app.router.routes[:] = routes
        ws._dashboard_plugins_cache = None
        client.close()


def test_private_execution_cas_and_manual_crud(private_client, monkeypatch):
    client, headers = private_client
    path = '/api/plugins/kanban/boards/default/execution'
    assert client.get(path).status_code == 401
    settings = client.get(path, headers=headers)
    assert settings.status_code == 200, settings.text
    assert settings.json()['enabled'] is False
    from hermes_cli import kanban_db_dispatch as dispatch
    monkeypatch.setattr(dispatch, '_default_spawn', lambda *a, **kw: pytest.fail('manual CRUD spawned a worker'))
    created = client.post('/api/plugins/kanban/tasks', headers=headers,
                          json={'title': '人工任务', 'status': 'todo'})
    assert created.status_code == 200, created.text
    task = created.json()['task']
    assert task['status'] == 'todo'
    assert 'warning' not in created.json()
    changed = client.patch('/api/plugins/kanban/tasks/' + task['id'], headers=headers, json={'title': '已编辑'})
    assert changed.json()['task']['title'] == '已编辑'
    assert client.patch('/api/plugins/kanban/tasks/' + task['id'], headers=headers,
                        json={'status': 'running'}).status_code == 400
    enabled = client.put(path, headers=headers, json={'enabled': True, 'expected_revision': 0})
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()['revision'] == 1
    assert client.put(path, headers=headers, json={'enabled': False, 'expected_revision': 0}).status_code == 409
    assert client.get('/api/plugins/kanban/boards/missing/execution', headers=headers).status_code == 404
    assert client.post('/api/plugins/kanban/dispatch?max=2', headers=headers).status_code == 422
