"""Profile isolation, retained login evidence and credential-free observations."""
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from plugins.operations import login_status
from plugins.operations.store import Store


def test_confirmed_login_persists_until_explicit_logout(tmp_path, monkeypatch):
    store = Store(tmp_path / "login.db")
    now = login_status.time.time()
    monkeypatch.setattr(login_status.time, "time", lambda: now)
    store.claim("one", busy=True)
    observation = {"worker": "one", "platform": "xiaohongshu", "state": "logged_in", "account_id": "mine"}
    login_status.observe(store, observation)
    confirmed = login_status.catalog(store, "one")["platforms"][0]["confirmed_at"]
    version, policy = store.policy()
    store.configure({**policy, "account_id": "different"}, version)
    row = login_status.catalog(store, "one")["platforms"][0]
    assert row["state"] == "logged_in" and row["account_mismatch"]
    now += 30 * 24 * 60 * 60
    offline = login_status.catalog(store, "one")
    assert not offline["worker_online"]
    assert offline["platforms"][0]["state"] == "logged_in"
    with pytest.raises(ValueError, match="离线"):
        login_status.observe(store, observation)
    store.claim("two", busy=True)
    for state in ("unknown", "verification"):
        login_status.observe(store, {**observation, "worker": "two", "state": state})
        row = login_status.catalog(store, "two")["platforms"][0]
        assert row["state"] == "logged_in" and row["observed_state"] == state
        assert row["account_id"] == "mine" and row["confirmed_at"] == confirmed
    login_status.observe(store, {**observation, "worker": "two", "state": "logged_out"})
    # New explicit logout also supersedes an older window's retained login record.
    for worker in ("one", "two"):
        row = login_status.catalog(Store(store.path), worker)["platforms"][0]
        assert row["state"] == "logged_out" and row["account_id"] == ""
    assert not store.snapshot()["actions"]


def test_existing_definite_observations_are_migrated_without_assuming_unknown_means_login(tmp_path):
    store = Store(tmp_path / "login.db")
    store.claim("one", busy=True)
    login_status.observe(store, {"worker": "one", "platform": "xiaohongshu", "state": "logged_in", "account_id": "mine"})
    login_status.observe(store, {"worker": "one", "platform": "zhihu", "state": "unknown"})
    with store.connection() as db:
        db.execute("DROP TABLE platform_login_evidence")
    migrated = Store(store.path)
    rows = {r["id"]: r for r in login_status.catalog(migrated)["platforms"]}
    assert rows["xiaohongshu"]["state"] == "logged_in"
    assert rows["zhihu"]["state"] == "unknown"
    assert Store(store.path).policy()[0] == store.policy()[0]


def test_private_login_api_is_profile_scoped_and_does_not_accept_credentials(tmp_path, monkeypatch):
    home = tmp_path / "home"
    work = home / "profiles" / "work"
    work.mkdir(parents=True)
    for directory in (home, work):
        (directory / "config.yaml").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(home))
    from hermes_cli import web_server
    prefix = "/api/plugins/operations"
    with TestClient(web_server.app) as client:
        assert client.get(prefix + "/platforms").status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        assert client.post(prefix + "/worker/poll?profile=work", json={"worker": "desktop", "busy": True}).status_code == 200
        body = {"worker": "desktop", "platform": "zhihu", "state": "logged_in", "account_id": "owner"}
        response = client.post(prefix + "/platforms/observe?profile=work", json=body)
        assert response.status_code == 200, response.text
        work_rows = client.get(prefix + "/platforms?profile=work&worker=desktop").json()["platforms"]
        assert next(r for r in work_rows if r["id"] == "zhihu")["state"] == "logged_in"
        default_rows = client.get(prefix + "/platforms?worker=desktop").json()["platforms"]
        assert all(r["state"] == "unchecked" for r in default_rows)
        for invalid in ({**body, "cookie": "not-a-real-cookie"}, {**body, "platform": "unsupported"}):
            assert client.post(prefix + "/platforms/observe?profile=work", json=invalid).status_code == 400
        assert client.post(prefix + "/platforms/observe", json=body).status_code == 400
