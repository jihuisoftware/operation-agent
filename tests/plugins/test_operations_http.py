"""Real host mount/auth/profile contract for the business plugin API."""
from starlette.testclient import TestClient


def test_private_plugin_api_requires_auth_and_scopes_profiles(tmp_path, monkeypatch):
    home = tmp_path / "home"
    work = home / "profiles" / "work"
    work.mkdir(parents=True)
    (home / "config.yaml").write_text("{}", encoding="utf-8")
    (work / "config.yaml").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    from hermes_cli import web_server
    with TestClient(web_server.app) as client:
        assert client.get("/api/plugins/operations/state").status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        response = client.get("/api/plugins/operations/state")
        assert response.status_code == 200, response.text
        body = response.json()
        body["policy"]["topic"] = "只属于默认配置"
        saved = client.put("/api/plugins/operations/policy", json={"version": body["version"], "policy": body["policy"]})
        assert saved.status_code == 200, saved.text
        secondary = client.get("/api/plugins/operations/state?profile=work")
        assert secondary.status_code == 200, secondary.text
        assert secondary.json()["policy"]["topic"] == ""


def test_content_pack_and_revocation_share_real_profile_assets(tmp_path, monkeypatch):
    import base64
    import json
    from io import BytesIO
    from zipfile import ZipFile
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from plugins.operations.store import Store
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    token = set_hermes_home_override(str(tmp_path))
    try:
        store = Store()
        store.put("source", {"day": "2026-10-31", "url": "https://example.org", "title": "来源", "text": "事实", "state": "read"}, "source")
        from hermes_cli import web_server
        with TestClient(web_server.app) as client:
            client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
            from PIL import Image
            image_file = BytesIO()
            Image.new("RGB", (2, 2), "white").save(image_file, format="PNG")
            image = client.post("/api/plugins/operations/assets", json={"name": "test.png", "data": base64.b64encode(image_file.getvalue()).decode(), "authorized": True})
            assert image.status_code == 200, image.text
            asset = image.json()["id"]
            body = {"title": "路线", "body": "事实引用", "asset_ids": [asset], "source_ids": ["source"], "ready": True}
            response = client.post("/api/plugins/operations/records/content", json=body)
            assert response.status_code == 200, response.text
            identity = response.json()["id"]
            package = client.get(f"/api/plugins/operations/content/{identity}/export")
            assert package.status_code == 200, package.text
            with ZipFile(BytesIO(base64.b64decode(package.json()["data"]))) as archive:
                assert json.loads(archive.read("content.json"))["body"] == "事实引用"
                assert any(name.startswith("images/") for name in archive.namelist())
            assert client.post(f"/api/plugins/operations/assets/{asset}/revoke").status_code == 200
            assert client.get(f"/api/plugins/operations/assets/{asset}").status_code == 404
            assert client.get(f"/api/plugins/operations/content/{identity}/export").status_code == 400
    finally:
        reset_hermes_home_override(token)


def test_blueprint_preview_apply_and_drafts_follow_host_profile_scope(tmp_path, monkeypatch):
    from pathlib import Path
    home = tmp_path / "home"
    work = home / "profiles" / "work"
    work.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(home))
    for profile in (home, work):
        (profile / "config.yaml").write_text("{}", encoding="utf-8")
    from hermes_cli import web_server
    with TestClient(web_server.app) as client:
        path = "/api/plugins/operations/blueprints"
        assert client.get(path).status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        catalog = client.get(path + "?profile=work").json()
        publishing = next(t for t in catalog["templates"] if t["id"] == "xiaohongshu-daily")
        assert publishing["kind"] == "scenario"
        assert "publish" in publishing["modules"]
        assert publishing["times"]["publish"] == ["10:00"]
        assert catalog["policy"]["allowed"]["publish"] is True
        assert not catalog["policy"]["enabled"]
        assert not any(catalog["policy"]["modules"].values())
        policy = catalog["policy"]
        policy.update(topic="次级配置主题", goal="只生成日报")
        policy["modules"]["report"] = True
        body = {"version": catalog["version"], "policy": policy, "request_id": "apply-work", "mode": "enable"}
        preview = client.post(path + "/preview?profile=work", json=body)
        assert preview.status_code == 200, preview.text
        assert not preview.json()["missing"]
        applied = client.post(path + "/apply?profile=work", json=body)
        assert applied.status_code == 200, applied.text
        assert client.post(path + "/apply?profile=work", json=body).json() == applied.json()
        default = client.get(path).json()
        assert default["policy"]["topic"] == ""
        assert not default["policy"]["enabled"]
        work_policy = client.get("/api/plugins/operations/state?profile=work").json()
        assert work_policy["policy"]["topic"] == "次级配置主题"
        assert work_policy["version"] == applied.json()["version"]
        body.update(mode="draft", request_id="draft-work", version=work_policy["version"])
        body["policy"]["topic"] = "仅保存草稿"
        assert client.post(path + "/apply?profile=work", json=body).status_code == 200
        assert client.get(path).json()["draft"] is None
        assert client.get(path + "?profile=work").json()["draft"]["policy"]["topic"] == "仅保存草稿"
