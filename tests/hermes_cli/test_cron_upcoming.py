"""Queue cancellation is authenticated and Profile scoped across core and plugin routes."""
from pathlib import Path
from starlette.testclient import TestClient


def test_cancel_routes_auth_and_owner(tmp_path, monkeypatch):
    from cron import jobs
    from hermes_cli import web_server
    from hermes_cli.web_routers.cron import _owner_home_scope
    home = tmp_path / 'home'
    work = home / 'profiles' / 'work'
    work.mkdir(parents=True)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('HERMES_HOME', str(home))
    for directory in (home, work):
        (directory / 'config.yaml').write_text('{}')
    with _owner_home_scope('work'):
        job = jobs.create_job(prompt='work task', schedule='every 1h')
    jobs.save_jobs([job])  # Same ID in two profile stores must remain independent.
    with TestClient(web_server.app) as client:
        assert client.get('/api/cron/upcoming').status_code in (401, 403)
        assert client.post('/api/plugins/operations/upcoming/cancel', json={}).status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        row = client.get('/api/cron/upcoming?profile=work').json()['jobs'][0]
        assert client.get('/api/cron/upcoming?profile=default').json()['jobs'][0]['state'] == 'pending'
        result = client.post(f"/api/cron/jobs/{job['id']}/cancel-next?profile=work", json=row)
        assert result.status_code == 200, result.text
        assert client.get('/api/cron/upcoming?profile=work').json()['jobs'][0]['state'] == 'cancelled'
        assert client.get('/api/cron/upcoming?profile=default').json()['jobs'][0]['state'] == 'pending'
        assert client.post('/api/plugins/operations/upcoming/cancel?profile=work', json={}).status_code == 400
