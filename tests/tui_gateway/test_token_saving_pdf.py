"""PDF rendering observes the owning session, before any file or subprocess work."""
import json
import threading

from tui_gateway import server


def test_pdf_permission_uses_session_profile_before_rendering(tmp_path, monkeypatch):
    launch, secondary = tmp_path / 'launch', tmp_path / 'secondary'
    launch.mkdir()
    secondary.mkdir()
    monkeypatch.setenv('HERMES_HOME', str(launch))
    monkeypatch.setattr(server, '_hermes_home', launch)
    (secondary / 'config.yaml').write_text(json.dumps({'token_saving': {'enabled': True, 'parse_images': True, 'parse_files': False}}))
    session = {'agent': None, 'agent_ready': threading.Event(), 'agent_error': None,
               'profile_home': str(secondary), 'cwd': str(tmp_path), 'running': False,
               'attached_images': [], 'history': [], 'session_key': 'token-pdf'}
    monkeypatch.setitem(server._sessions, 'token-pdf', session)
    params = {'session_id': 'token-pdf', 'content_base64': 'JVBERi0xLjQK'}
    # If it reaches the renderer lookup this returns its usual missing-tool error.
    monkeypatch.setattr('shutil.which', lambda _: None)
    response = server._methods['pdf.attach'](1, params)
    assert response['error']['code'] == 4017
    assert '节省 Token' in response['error']['message']
    assert not session['attached_images']
    session['profile_home'] = str(launch)
    response = server._methods['pdf.attach'](2, params)
    assert response['error']['code'] == 5028
