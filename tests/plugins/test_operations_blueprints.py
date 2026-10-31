"""Blueprint composition uses the real policy store, occurrence ledger and cron jobs."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, UTC
import json

import pytest

from plugins.operations import blueprints, workflow
from plugins.operations.policy import DEFAULT
from plugins.operations.runtime import tick
from plugins.operations.store import Store, encoded


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return Store(tmp_path / "plan.db")


def request(store, *, mode="enable", request_id="one", modules=("research", "content", "report")):
    version, policy = store.policy()
    policy.update(topic="城市步行", goal="整理真实路线")
    policy["modules"] = {key: key in modules for key in policy["modules"]}
    return {"version": version, "policy": policy, "request_id": request_id, "mode": mode}


def test_draft_does_not_mutate_live_policy_and_offline_modules_need_no_account(store):
    body = request(store)
    active = blueprints.apply(store, body)
    assert active["version"] == 1
    assert store.policy()[1]["account_id"] == ""
    body = request(store, mode="draft", request_id="draft", modules=("publish",))
    body["policy"]["topic"] = "尚未确定的方向"
    missing = blueprints.preview(store, body)["missing"]
    assert "publish" in missing
    blueprints.apply(store, body)
    assert store.policy()[1]["topic"] == "城市步行"
    assert store.policy()[0] == 1
    assert store.objects("blueprint_draft")[0]["policy"]["topic"] == "尚未确定的方向"


def test_scenario_choice_can_be_customized_without_scheduling_on_catalog_read(store):
    from cron.jobs import list_jobs

    before = store.policy()
    catalog = blueprints.catalog(store)
    scenario = next(t for t in catalog["templates"] if t["id"] == "industry-watch")
    assert store.policy() == before
    assert list_jobs() == []
    policy = deepcopy(catalog["policy"])
    policy.update(scenario["defaults"], topic="城市步行", goal="跟进无障碍路线的新信息")
    policy["modules"] = {key: key in scenario["modules"] for key in policy["modules"]}
    policy["times"]["research"] = ["08:30"]
    policy["times"]["report"] = ["20:30"]
    policy["limits"]["source"] = 2
    body = {"version": catalog["version"], "policy": policy, "request_id": "scenario", "mode": "enable"}
    preview = blueprints.preview(store, body)
    assert preview["missing"] == {}
    assert [r["time"] for r in preview["timeline"]] == ["08:30", "20:30"]
    blueprints.apply(store, body)
    blueprints.apply(store, body)
    saved = store.policy()[1]
    assert saved["goal"] == "跟进无障碍路线的新信息"
    assert saved["limits"]["source"] == 2
    assert not any(saved["allowed"].values())
    assert len(list_jobs()) == 1


def test_repeat_and_concurrent_application_keep_one_plan_and_one_schedule(store):
    from cron.jobs import list_jobs
    body = request(store)
    body["policy"]["limits"]["source"] = 3
    def apply_same(_):
        return blueprints.apply(Store(store.path), deepcopy(body))
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(apply_same, range(3)))
    assert {r["version"] for r in responses} == {1}
    assert len({r["job_id"] for r in responses}) == 1
    assert store.policy()[1]["limits"]["source"] == 3
    assert all(not value for value in store.policy()[1]["allowed"].values())
    assert len([j for j in list_jobs() if j.get("no_agent")]) == 1
    changed = deepcopy(body)
    changed["policy"]["goal"] = "不同请求不能冒用 ID"
    with pytest.raises(ValueError, match="同一请求 ID"):
        blueprints.apply(store, changed)


def test_stale_editor_and_incomplete_permissions_cannot_enable(store):
    body = request(store, modules=("dm", "follow"))
    body["policy"]["allowed"].update(dm=True, follow=True)
    body["policy"]["account_id"] = "me"
    with pytest.raises(ValueError, match="回复知识"):
        blueprints.apply(store, body)
    assert store.policy()[0] == 0
    blueprints.apply(store, request(store, request_id="new"))
    with pytest.raises(ValueError, match="配置已变更"):
        blueprints.apply(store, body)


def test_removing_module_cancels_queued_action_and_preserves_history(store):
    body = request(store, modules=("comments",))
    body["policy"]["account_id"] = "me"
    body["policy"]["allowed"]["comment"] = True
    blueprints.apply(store, body)
    action = {"kind": "comment", "account_id": "me", "target": "note", "text": "评论"}
    identity = store.reserve_action(action, 1)
    store.enqueue("interact", action, identity)
    blueprints.apply(store, request(store, modules=("report",), request_id="remove"))
    assert store.snapshot()["actions"][0]["state"] == "cancelled"
    assert not store.policy()[1]["allowed"]["comment"]
    with pytest.raises(ValueError, match="未授权"):
        store.reserve_action({**action, "target": "another"}, 2)


def test_old_rules_and_claimed_occurrences_migrate_once_without_replay(store):
    old = deepcopy(DEFAULT)
    old.pop("modules")
    old.pop("schema_version")
    old.update(enabled=True, topic="旧主题", goal="旧目标", account_id="me")
    old["allowed"].update(comment=True, dm=True, follow=True, publish=True)
    old["limits"]["comment"] = 2
    old["times"] = {"research": ["08:30"], "publish": ["10:10"], "interact": ["11:20"], "report": ["20:00"]}
    with store.connection() as db:
        db.execute("UPDATE settings SET version=4,data=?", (encoded(old),))
    run = store.start_run("2026-10-31", "interact", "11:20", 4)
    store.finish_run(run, "completed", "旧流程已处理")
    with store.connection() as db:
        db.execute("UPDATE runs SET started='2026-10-31T03:20:00+00:00', ended='2026-10-31T03:20:10+00:00' WHERE id=?", (run,))
    migrated = Store(store.path)
    version, policy = migrated.policy()
    assert version == 5
    assert policy["limits"]["comment"] == 2
    assert policy["times"]["content"] == ["10:10"]
    assert all(policy["times"][m] == ["11:20"] for m in ("comments", "dm", "follow"))
    assert Store(store.path).policy()[0] == 5
    migrated.claim("desktop", busy=True)
    tick(migrated, datetime(2026, 10, 31, 3, 21, tzinfo=UTC))
    assert not migrated.snapshot()["actions"]
    assert any(r["stage"] == "interact" for r in migrated.snapshot()["runs"])
    assert len([r for r in migrated.snapshot()["runs"] if r["state"] == "migrated"]) == 3
    from plugins.operations.report import daily_report
    assert "耗时合计 10.0 秒" in daily_report(migrated, "2026-10-31")["markdown"]


def test_production_without_images_is_a_draft_and_publishing_never_generates_a_new_post(store, monkeypatch):
    from plugins.operations import content
    body = request(store)
    blueprints.apply(store, body)
    version, policy = store.policy()
    store.put("source", {"day": "2026-10-31", "url": "https://example.org", "text": "真实资料", "fingerprint": "source"}, "source")
    calls = []
    def generate(*args):
        calls.append(args[-1])
        return {"title": "路线", "body": "真实资料", "asset_ids": [], "source_ids": ["source"]} if "assets" in args[-1] else {"pass": True}
    monkeypatch.setattr(content, "generate", generate)
    result = workflow.produce(store, policy, "2026-10-31", version)
    assert not result["ready"]
    assert store.objects("content")[0]["state"] == "needs_material"
    assert not store.snapshot()["actions"]
    policy["allowed"]["publish"] = True
    from plugins.operations.outcomes import StageSkipped
    with pytest.raises(StageSkipped, match="没有选定"):
        workflow.publish(store, policy, "2026-10-31", version)
    assert len(calls) == 2


def test_publication_uses_selected_version_and_rechecks_revoked_material(store, monkeypatch):
    from plugins.operations import content
    body = request(store, modules=("publish",))
    body["policy"].update(account_id="me")
    body["policy"]["allowed"]["publish"] = True
    store.put("asset", {"name": "自有图.png", "authorized": True}, "image")
    blueprints.apply(store, body)
    store.put("source", {"text": "来源资料"}, "source")
    saved = {"day": "2026-10-31", "title": "已选标题", "body": "已选正文", "asset_ids": ["image"], "source_ids": ["source"], "ready": True}
    store.put("content", saved, "revision")
    seen = []
    monkeypatch.setattr(content, "generate", lambda *args: {"pass": True})
    monkeypatch.setattr(workflow, "browser", lambda store, kind, payload, identity: seen.append(payload))
    version, policy = store.policy()
    workflow.publish(store, policy, "2026-10-31", version)
    assert seen[0]["content"]["id"] == "revision"
    assert seen[0]["content"]["body"] == "已选正文"
    with store.connection() as db:
        db.execute("UPDATE objects SET data=? WHERE id='image'", (json.dumps({"authorized": True, "revoked": True}),))
    with pytest.raises(ValueError, match="素材不匹配"):
        workflow.publish(store, policy, "2026-10-31", version)


def test_reapply_resumes_existing_schedule_and_catalog_reports_paused_scheduler(store):
    from cron.jobs import pause_job, get_job, list_jobs
    first = blueprints.apply(store, request(store))
    pause_job(first["job_id"])
    assert blueprints.catalog(store)["schedule_state"] == "paused"
    assert blueprints.catalog(store)["next_at"] is None
    second = blueprints.apply(store, request(store, request_id="resume"))
    assert second["job_id"] == first["job_id"]
    assert get_job(first["job_id"])["enabled"]
    assert len(list_jobs()) == 1
