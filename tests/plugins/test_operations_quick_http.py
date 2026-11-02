"""New controls are authenticated and remain isolated in a multiplexed host."""
from starlette.testclient import TestClient


def test_quick_plan_controls_and_library_belong_to_requested_profile(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    work = tmp_path / 'profiles' / 'work'
    work.mkdir(parents=True)
    (tmp_path / 'config.yaml').write_text('{}')
    (work / 'config.yaml').write_text('{}')
    from hermes_cli import web_server
    with TestClient(web_server.app) as client:
        base = '/api/plugins/operations'
        assert client.get(base + '/quick-start').status_code in {401, 403}
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        scope = {'profile': 'work'}
        initial = client.get(base + '/blueprints', params=scope).json()
        policy = initial['policy']
        policy.update(topic='机械零件加工', goal='真实材料分析')
        policy['modules'].update(research=True, publish=True, dm=True, report=True)
        body = {'version': initial['version'], 'policy': policy, 'request_id': 'same-first', 'start': True}
        preview = client.post(base + '/blueprints/preview', params=scope, json=body).json()
        assert not preview['blocking'] and not preview['readiness']['publish']['ready']
        saved = client.post(base + '/quick-start', params=scope, json=body)
        assert saved.status_code == 200, saved.text
        assert client.post(base + '/quick-start', params=scope, json=body).json()['version'] == 1
        assert client.get(base + '/quick-start').json()['run'] is None
        assert client.get(base + '/quick-start', params=scope).json()['run']['state'] == 'pending'
        current = client.get(base + '/policy', params=scope).json()
        reopened = {**body, 'version': current['version'], 'policy': current['policy'], 'request_id': 'after-reopen'}
        assert client.post(base + '/quick-start', params=scope, json=reopened).json()['reused']
        held = client.post(base + '/worker/takeover', params=scope, json={'worker': 'desktop', 'active': True})
        assert held.status_code == 200
        assert client.get(base + '/policy', params=scope).json()['web_held']
        assert not client.get(base + '/policy').json()['web_held']
        assert not client.get(base + '/policy', params=scope).json()['policy']['paused']
        pause = client.post(base + '/plan/control', params=scope, json={'version': 1, 'action': 'pause'})
        assert pause.status_code == 200, pause.text
        client.post(base + '/worker/takeover', params=scope, json={'worker': 'new-window', 'active': False})
        assert client.get(base + '/policy', params=scope).json()['policy']['paused']
        assert not client.get(base + '/policy').json()['policy']['paused']
        assert client.get(base + '/library/assets', params=scope).json()['asset'] == []
        assert client.get(base + '/library/assets', params={'before': -1}).status_code == 400
        assert client.post(base + '/plan/control', params=scope, json={'version': 1, 'action': 'run'}).status_code == 400
        assert client.get(base + '/quick-start', params=scope).json()['run']['version'] == 1
