"""Desktop keeps its backend handshake after the browser frontend is retired."""

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from hermes_cli.web_server_backend import mount_backend_root


def test_backend_ignores_leftover_web_bundle_and_keeps_api_routes(tmp_path, monkeypatch):
    from hermes_cli import web_server

    dist = tmp_path / "web_dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("retired dashboard", encoding="utf-8")
    (dist / "assets/old.js").write_text("retired bundle", encoding="utf-8")
    monkeypatch.setenv("HERMES_WEB_DIST", str(dist))
    monkeypatch.delenv("HERMES_SERVE_HEADLESS", raising=False)
    monkeypatch.setattr(web_server.app.state, "withhold_session_token", False, raising=False)
    app = FastAPI()

    @app.get("/api/probe")
    def probe():
        return {"ready": True}

    mount_backend_root(app)
    client = TestClient(app)
    root = client.get("/")
    assert root.status_code == 200
    assert web_server._SESSION_TOKEN in root.text
    assert "retired dashboard" not in root.text
    assert "no-store" in root.headers["cache-control"]
    assert client.get("/api/probe").json() == {"ready": True}
    for path in ("/chat", "/settings", "/assets/old.js"):
        assert client.get(path).status_code == 404


@pytest.mark.parametrize("gated,withheld", [(True, False), (False, True)])
def test_backend_root_never_bootstraps_a_protected_listener_token(monkeypatch, gated, withheld):
    from hermes_cli import web_server

    app = FastAPI()
    app.state.auth_required = gated
    monkeypatch.setattr(web_server.app.state, "withhold_session_token", withheld, raising=False)
    mount_backend_root(app)
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert web_server._SESSION_TOKEN not in response.text
    assert "__HERMES_SESSION_TOKEN__" not in response.text
    assert "no-store" in response.headers["cache-control"]
