"""Task details use the existing authenticated, profile-owned HTTP path."""
import json
from pathlib import Path

from starlette.testclient import TestClient


def test_task_details_auth_and_profile_isolation(tmp_path, monkeypatch):
    from cron import jobs, executions, task_history
    from hermes_cli import web_server
    from hermes_cli.web_routers.cron import _owner_home_scope

    home = tmp_path / 'home'
    work = home / 'profiles' / 'work'
    work.mkdir(parents=True)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('HERMES_HOME', str(home))
    for directory in (home, work):
        (directory / 'config.yaml').write_text('{}')
    job = jobs.create_job(prompt='default task', schedule='every 1h')
    (work / 'cron').mkdir()
    (work / 'cron' / 'jobs.json').write_text(json.dumps({'jobs': [{**job, 'prompt': 'work task'}]}))
    with _owner_home_scope('work'):
        attempt = executions.create_execution(job['id'], source='manual')
        executions.mark_execution_running(attempt['id'])
        task_history.save_output(attempt['id'], '工作成果')
        executions.finish_execution(attempt['id'], success=True)
    url = f"/api/cron/jobs/{job['id']}/details"
    with TestClient(web_server.app) as client:
        assert client.get(url).status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        response = client.get(url, params={'profile': 'work'})
        assert response.status_code == 200, response.text
        assert response.json()['output'] == '工作成果'
        assert response.json()['snapshot']['prompt'] == 'work task'
        assert client.get(url, params={'profile': 'default'}).json()['execution'] is None
        assert client.get(url, params={'profile': 'default', 'execution_id': attempt['id']}).status_code == 404
