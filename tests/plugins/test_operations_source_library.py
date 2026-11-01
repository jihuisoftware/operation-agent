"""Collected picture/text snapshots are reusable evidence, never automatic publishing assets."""
from copy import deepcopy
from io import BytesIO
import json

import httpx
from PIL import Image
import pytest

from plugins.operations import collection, content, source_library, source_media, topics
from plugins.operations.policy import DEFAULT
from plugins.operations.store import Store


def configured(tmp_path):
    store = Store(tmp_path / "operations.db")
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic="收纳", goal="有依据的整理方法", sources=["https://example.org/a"])
    policy["modules"].update(research=True, topics=True, content=True)
    store.configure(policy, 0)
    return store, policy


def png():
    buffer = BytesIO()
    Image.new("RGB", (3, 2), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_collection_persists_images_text_and_provenance_and_can_reuse_across_days(tmp_path, monkeypatch):
    store, policy = configured(tmp_path)
    from tools import web_tools
    monkeypatch.setattr(web_tools, "web_search_tool", lambda *a, **k: '{"data":{"web":[]}}')
    async def extract(*args, **kwargs):
        return json.dumps({"results": [{"content": "收纳原文 ![参考](/picture.png)", "images": ["/bad.png"],
                                        "author": "原作者", "published_at": "2026-10-30"}]})
    monkeypatch.setattr(web_tools, "web_extract_tool", extract)
    fetched = []
    def download(url):
        fetched.append(url)
        if url.endswith("bad.png"):
            raise ValueError("图片不可用")
        return png()
    monkeypatch.setattr(source_media, "download", download)
    collection.collect(store, policy, "2026-10-31")
    collection.collect(store, policy, "2026-10-31")
    assert len(fetched) == 2
    source = store.objects("source")[0]
    assert source["author"] == "原作者" and "收纳原文" in source["text"]
    assert source["images"][0]["state"] == "unavailable"
    image = source["images"][1]
    assert (source_media.directory(store) / image["id"]).read_bytes() == png()
    assert not store.objects("asset") and image["authorized"] is False
    assert not source_library.available_sources(store, policy, "2026-11-01")
    source_library.reuse(store, source["id"], {"version": 1, "enabled": True})
    from tests.plugins.operations_support import prepare_materials
    prepare_materials(store, policy, "2026-11-01", monkeypatch)
    seen = []
    def generate(*args):
        seen.append(args[-1])
        return {"topics": [{"title": "收纳步骤", "source_ids": [source["id"]]}]}
    monkeypatch.setattr(topics, "generate", generate)
    topics.generate_topics(store, policy, "2026-11-01", 1)
    assert seen[0]["sources"][0]["id"] == source["id"]
    def produce(*args):
        assert args[-1]["sources"][0]["images"] == source["images"]
        assert not args[-1]["assets"]
        return {"title": "收纳步骤", "body": "有依据的整理", "source_ids": [source["id"]], "asset_ids": []}
    monkeypatch.setattr(content, "generate", produce)
    monkeypatch.setattr(content, "check_content", lambda *args: {"pass": True})
    result = content.produce_content(store, policy, "2026-11-01", 1)
    assert not result["ready"]
    assert source_library.detail(store, source["id"])["content_versions"][0]["id"] == result["content_id"]


def test_pins_are_topic_scoped_version_checked_and_search_has_stable_pages(tmp_path):
    store, policy = configured(tmp_path)
    for i in range(26):
        store.put("source", {"title": f"资料 {i}", "text": "收纳资料", "state": "read", "day": "2026-10-31", "fingerprint": str(i)}, str(i))
    first = source_library.catalog(store, "收纳")
    second = source_library.catalog(store, "收纳", first["next_cursor"])
    assert first["total"] == 26 and len(second["items"]) == 2
    assert not {r["id"] for r in first["items"]} & {r["id"] for r in second["items"]}
    source_library.reuse(store, "1", {"version": 1, "enabled": True})
    source_library.reuse(store, "1", {"version": 1, "enabled": True})
    assert source_library.catalog(store)["selected_count"] == 1
    assert [r["id"] for r in source_library.available_sources(store, policy, "2026-11-02")] == ["1"]
    assert not source_library.available_sources(store, {**policy, "topic": "别的主题"}, "2026-11-02")
    source_library.reuse(store, "1", {"version": 1, "enabled": False})
    assert not source_library.available_sources(store, policy, "2026-11-02")
    with pytest.raises(ValueError, match="规则已变更"):
        source_library.reuse(store, "1", {"version": 0, "enabled": True})


def test_image_fetch_rejects_private_redirects_and_invalid_images(tmp_path, monkeypatch):
    from tools import url_safety
    seen = []
    def respond(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
    monkeypatch.setattr(url_safety, "create_ssrf_safe_client", lambda **kwargs: httpx.Client(transport=httpx.MockTransport(respond)))
    with pytest.raises(ValueError, match="图片地址不可访问"):
        source_media.download("https://93.184.216.34/picture")
    assert len(seen) == 1
    monkeypatch.setattr(source_media, "download", lambda url: b"<html>not an image</html>")
    store, _ = configured(tmp_path)
    result = source_media.capture(store, ["https://example.org/bad"], "https://example.org")
    assert result[0]["state"] == "unavailable" and not store.objects("source_image")


def test_library_and_local_images_follow_private_api_profile_scope(tmp_path, monkeypatch):
    from pathlib import Path
    from starlette.testclient import TestClient
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    other = tmp_path / "profiles" / "other"
    other.mkdir(parents=True)
    for home in (tmp_path, other):
        (home / "config.yaml").write_text("{}")
    token = set_hermes_home_override(str(tmp_path))
    try:
        store = Store()
        store.put("source", {"title": "私有来源", "url": "https://example.org", "text": "正文"}, "s")
        monkeypatch.setattr(source_media, "download", lambda url: png())
        identity = source_media.save_image(store, "https://example.org/image")
        from hermes_cli import web_server
        with TestClient(web_server.app) as client:
            base = "/api/plugins/operations/sources"
            assert client.get(base).status_code in (401, 403)
            client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
            assert client.get(base).json()["items"][0]["title"] == "私有来源"
            assert client.get(base + "/s").json()["text"] == "正文"
            assert client.get(base + f"/images/{identity}").json()["mime"] == "image/png"
            assert client.get(base + "/s?profile=other").status_code == 404
            assert client.get(base + f"/images/{identity}?profile=other").status_code == 404
    finally:
        reset_hermes_home_override(token)
