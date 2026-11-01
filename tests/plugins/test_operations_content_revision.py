"""Publishing a revised draft compares against releases, not its own working copies."""
from copy import deepcopy

from plugins.operations import content, workflow
from plugins.operations.policy import DEFAULT
from plugins.operations.store import Store


def test_publish_checks_releases_and_supplies_asset_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    store = Store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic="创作", goal="帮助创作者", account_id="me")
    policy["allowed"]["publish"] = True
    policy["modules"]["publish"] = True
    version = store.configure(policy, 0)
    day = "2026-11-01"
    store.put("source", {"text": "定位要具体", "day": day}, "source")
    store.put("asset", {"authorized": True, "name": "原创文字封面.png"}, "cover")
    old = {"title": "个人号定位", "body": "定位要具体", "source_ids": ["source"], "asset_ids": [], "day": day}
    store.put("content", old, "old-draft")
    revised = {**old, "body": old["body"] + "。参考原始来源。", "asset_ids": ["cover"], "ready": True}
    store.put("content", revised, "selected")
    released = {**old, "title": "已发布内容", "body": "已经发布的经验", "id": "release"}
    prior = store.reserve_action({"kind": "publish", "account_id": "me", "target": "release", "content": released}, version, "2026-10-31")
    with store.connection() as db:
        db.execute("UPDATE actions SET state='published' WHERE id=?", (prior,))

    def review(_store, _policy, _day, _instruction, data):
        assert data["history"] == [released]
        assert data["assets"][0]["name"] == "原创文字封面.png"
        return {"pass": True, "reason": "检查通过"}

    monkeypatch.setattr(content, "generate", review)
    monkeypatch.setattr(workflow, "browser", lambda *_args: {"state": "published", "evidence": "模拟发布回执"})
    assert workflow.publish(store, policy, day, version)["state"] == "published"
    check = store.objects("check")[0]["result"]
    assert check["scope"] == "text_and_asset_metadata"
    assert check["visual_review"] == "not_performed"
