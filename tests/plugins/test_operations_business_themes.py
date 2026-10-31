"""Business presets authorize default modules while retaining editable rules and prerequisites."""
from copy import deepcopy
import json

import pytest

from plugins.operations import blueprints
from plugins.operations.business_themes import BUSINESS_THEMES
from plugins.operations.policy import DEFAULT, validate_policy
from plugins.operations.store import Store


@pytest.mark.parametrize("theme", BUSINESS_THEMES, ids=lambda theme: theme["id"])
def test_business_configuration_round_trip_keeps_one_schedule(tmp_path, monkeypatch, theme):
    from cron.jobs import list_jobs

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    store = Store(tmp_path / "plan.db")
    catalog = blueprints.catalog(store)
    preset = next(item for item in catalog["templates"] if item["id"] == theme["id"])
    assert list_jobs() == []
    policy = deepcopy(catalog["policy"])
    policy.update(preset["defaults"], business_theme=preset["id"], business_subtype=preset["subtypes"][0])
    policy["goal"] = "我修改后的真实业务目标"
    policy["modules"] = {key: key in preset["modules"] for key in policy["modules"]}
    policy["times"]["research"] = ["08:30"]
    policy["limits"]["source"] = 2
    body = {"version": catalog["version"], "policy": policy, "mode": "draft", "request_id": "draft"}
    blueprints.apply(store, body)
    assert store.objects("blueprint_draft")[0]["policy"]["business_subtype"] == preset["subtypes"][0]
    assert store.policy()[1]["business_theme"] == ""
    assert list_jobs() == []
    with pytest.raises(ValueError, match="运行条件"):
        blueprints.apply(store, {**body, "mode": "enable", "request_id": "missing"})
    policy.update(account_id="mock-account", knowledge=["开放时间为九点"])
    store.put("asset", {"authorized": True, "name": "模拟图片"}, "mock-image")
    body.update(mode="enable", request_id="enable")
    blueprints.apply(store, body)
    blueprints.apply(store, body)
    saved = Store(store.path).policy()[1]
    assert saved["business_theme"] == preset["id"]
    assert saved["business_subtype"] == preset["subtypes"][0]
    assert saved["goal"] == "我修改后的真实业务目标"
    assert saved["times"]["research"] == ["08:30"]
    assert saved["limits"]["source"] == 2
    assert saved["knowledge"] == policy["knowledge"]
    assert all(saved["allowed"][a] for a in ("publish", "comment", "reply", "dm"))
    assert not saved["allowed"]["follow"]
    selected = [t for t in blueprints.catalog(store)["templates"] if t.get("kind") == "business" and t["status"] == "已加入"]
    assert [t["id"] for t in selected] == [preset["id"]]
    assert len(list_jobs()) == 1


def test_old_policy_load_and_invalid_business_selection(tmp_path):
    old = deepcopy(DEFAULT)
    old.pop("business_theme")
    old.pop("business_subtype")
    old["topic"] = "已有主题"
    store = Store(tmp_path / "old.db")
    with store.connection() as db:
        db.execute("UPDATE settings SET version=7,data=?", (json.dumps(old),))
    version, policy = Store(store.path).policy()
    assert version == 7
    assert policy["topic"] == "已有主题"
    assert policy["business_theme"] == policy["business_subtype"] == ""
    for theme, subtype in [("missing", ""), ("", "源头工厂"), ("business-factory", "餐饮")]:
        with pytest.raises(ValueError, match="业务"):
            validate_policy({**policy, "business_theme": theme, "business_subtype": subtype})
