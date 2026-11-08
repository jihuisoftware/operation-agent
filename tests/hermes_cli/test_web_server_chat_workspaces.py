"""Dashboard chat workspace picker: ``GET /api/chat/workspaces`` + ``/api/pty?cwd=``.

A fresh dashboard chat can be aimed at a host directory (the same projects/repos the
Desktop sidebar lists); the pick reaches the TUI as ``HERMES_CWD``/``HERMES_TUI_CWD`` and a
dead path fails closed instead of silently landing in the dashboard's launch dir.
"""

from pathlib import Path

import pytest
from fastapi import HTTPException

from hermes_cli import web_server, web_server_chat
from hermes_cli.web_routers import chat_workspaces

pytest.importorskip("starlette.testclient")
from starlette.testclient import TestClient


@pytest.fixture
def client():
    previous = getattr(web_server.app.state, "auth_required", None)
    web_server.app.state.auth_required = False
    test_client = TestClient(web_server.app)
    test_client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
    try:
        yield test_client
    finally:
        if previous is None:
            try:
                delattr(web_server.app.state, "auth_required")
            except AttributeError:
                pass
        else:
            web_server.app.state.auth_required = previous


def test_workspaces_lists_projects_and_discovered_repos(client, tmp_path):
    """Explicit project folders AND the discovery cache both surface; the payload names the
    default cwd a chat lands in when nothing is picked."""
    from hermes_cli import projects_db as pdb

    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    repo_dir = tmp_path / "scanned"
    repo_dir.mkdir()
    with pdb.connect_closing() as conn:
        pdb.create_project(conn, name="Demo", folders=[str(proj_dir)])
        pdb.record_discovered_repos(conn, [(str(repo_dir), "scanned")], replace=True, policy_key="k")

    body = client.get("/api/chat/workspaces").json()

    assert [p["name"] for p in body["projects"]] == ["Demo"]
    assert body["projects"][0]["folders"][0]["path"] == str(proj_dir)
    assert str(repo_dir) in {r["root"] for r in body["repos"]}
    assert Path(body["default_cwd"]).is_dir()
    assert body["home"] == str(Path.home())
