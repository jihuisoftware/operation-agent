"""Complete run output stays authenticated, profile-owned and on-demand."""
import json
from pathlib import Path

from starlette.testclient import TestClient


def test_full_output_auth_profile_and_file_boundary(tmp_path, monkeypatch):
    from cron import jobs
    from hermes_cli import web_server

    home = tmp_path / 'home'
    work = home / 'profiles' / 'work'
    work.mkdir(parents=True)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('HERMES_HOME', str(home))
    for directory in (home, work):
        (directory / 'config.yaml').write_text('{}')
    job = jobs.create_job(prompt='test', schedule='every 1h')
    filename = '2026-10-31_18-24-51.md'
    full_text = '# Cron Job: test\n\n---\n\n手动运营：待完善 1\n' + '完整信息\n' * 300 + 'END-OF-OUTPUT'
    for directory, text in ((home, 'default output'), (work, full_text)):
        output = directory / 'cron' / 'output' / job['id']
        output.mkdir(parents=True)
        (directory / 'cron' / 'jobs.json').write_text(json.dumps({'jobs': [job]}))
        (output / filename).write_text(text)
    from hermes_cli.web_routers.cron import _cron_output_run_preview
    assert _cron_output_run_preview(work / 'cron' / 'output' / job['id'] / filename).startswith('手动运营：待完善 1')
    url = f"/api/cron/jobs/{job['id']}/output"
    with TestClient(web_server.app) as client:
        assert client.get(url, params={'filename': filename}).status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        result = client.get(url, params={'filename': filename, 'profile': 'work'})
        assert result.status_code == 200, result.text
        assert result.json()['output'].endswith('END-OF-OUTPUT')
        assert result.json()['output'] == full_text
        assert len(result.json()['output']) > 180
        assert result.json()['profile'] == 'work'
        assert client.get(url, params={'filename': filename, 'profile': 'default'}).json()['output'] == 'default output'
        assert client.get(url, params={'filename': '../config.yaml', 'profile': 'work'}).status_code == 400
        path = work / 'cron' / 'output' / job['id'] / filename
        path.unlink()
        assert client.get(url, params={'filename': filename, 'profile': 'work'}).status_code == 404
        path.symlink_to(home / 'config.yaml')
        assert client.get(url, params={'filename': filename, 'profile': 'work'}).status_code == 404
