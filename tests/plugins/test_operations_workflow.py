"""A complete simulated day through the real scheduler, providers, queue and report ledger."""
from copy import deepcopy
from datetime import datetime, UTC
import json
from types import SimpleNamespace

import pytest
from plugins.operations.policy import DEFAULT
from plugins.operations.runtime import tick, ensure_schedule
from plugins.operations.store import Store
from plugins.operations import service


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    store = Store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic="步行", goal="路线信息", account_id="me", sources=["https://example.org/a", "https://example.org/b", "https://example.org/offline"], knowledge=["开放时间为九点。"], follow_terms=["步行"])
    policy["allowed"] = {k: True for k in policy["allowed"]}
    policy["modules"] = {k: True for k in policy["modules"]}
    store.configure(policy, 0)
    return store


def fake_model(**kwargs):
    data = json.loads(kwargs["messages"][1]["content"])
    if data.get('task') == 'industry_analysis':
        from tests.plugins.operations_support import industry_response as finding
        result = finding(data)
    elif data.get("task") == "organize_sources":
        from tests.plugins.operations_support import organized_response
        result = organized_response(data)
    elif "candidates" in data:
        result = {"actions": [{"id": data["candidates"][0]["id"], "text": "开放时间为九点。", "knowledge_ids": [0], "reason": "已确认知识"}]}
    elif "content" in data:
        assert all(c["body"] != data["content"]["body"] for c in data["history"])
        result = {"pass": True, "reason": "有原始来源，符合主题"}
    elif "assets" in data:
        result = {"title": "步行路线", "body": "路线信息来自原始资料。", "asset_ids": ["image"], "source_ids": [data["sources"][0]["id"]]}
    else:
        result = {"facts": [{"text": "路线开放", "source_ids": [s["id"] for s in data["sources"]]}], "opinions": [], "unknowns": [], "topics": ["步行路线"]}
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(result)))], usage=SimpleNamespace(model_dump=lambda: {"total_tokens": 20}))


@pytest.mark.parametrize("manual", [False, True])
@pytest.mark.parametrize("automatic_account", [False, True])
def test_full_day_is_traceable_idempotent_and_reports_actual_outcomes(store, monkeypatch, manual, automatic_account):
    from agent import auxiliary_client
    from tools import web_tools
    monkeypatch.setattr(auxiliary_client, "call_llm", fake_model)
    monkeypatch.setattr(web_tools, "web_search_tool", lambda *args, **kwargs: json.dumps({"data": {"web": []}}))
    async def extract(urls, **kwargs):
        return json.dumps({"results": [{"content": "同一份真实路线资料"} if "offline" not in urls[0] else {"error": "不可访问"}]})
    monkeypatch.setattr(web_tools, "web_extract_tool", extract)
    store.put("asset", {"authorized": True, "name": "自有图片.png"}, "image")
    from plugins.operations.blueprints import apply, preview
    version, policy = store.policy()
    if automatic_account:
        policy["account_id"] = ""
    if manual:
        policy["limits"]["publish"] = 2
    request = {"version": version, "policy": policy, "mode": "enable", "request_id": "full-day"}
    assert not preview(store, request)["missing"]
    assert apply(store, request)["job_id"]
    from plugins.operations.login_status import observe
    store.claim('simulated-desktop', busy=True)
    observe(store, {'worker': 'simulated-desktop', 'platform': 'xiaohongshu', 'state': 'logged_in', 'account_id': 'me'})
    original = store.command
    submissions = []
    def consume(identity):
        command = store.claim("simulated-desktop")
        while command and command['kind'] == 'verify' and command['id'] != identity:
            store.acknowledge(command['id'], 'simulated-desktop', {'state': 'unknown', 'evidence': '只读核对：平台仍在审核'})
            command = store.claim('simulated-desktop')
        assert command["id"] == identity
        payload = command["payload"]
        if command["kind"] == "account":
            result = {"account_id": "me"}
        elif command["kind"] == "verify":
            result = {"state": "unknown", "evidence": "平台仍在审核"}
        elif command["kind"] == "inbox":
            result = {"items": [{"id": payload["kind"] + ":1", "text": "步行，开放时间？", "inbound": True, "follows_me": True}], "evidence": "模拟网页可见条目"}
        else:
            submissions.append(payload["kind"])
            result = {"state": "submitted" if payload["kind"] == "publish" and not manual else "confirmed", "evidence": "模拟平台回执", "url": "https://example.org/result"}
        store.acknowledge(identity, "simulated-desktop", result)
        return original(identity)
    monkeypatch.setattr(store, "command", consume)
    if manual:
        for batch in ("first-click", "first-click", "second-click"):
            store.claim("simulated-desktop", busy=True)
            tick(store, datetime(2026, 10, 31, 9, 45, tzinfo=UTC), request_id=batch)
        assert len(store.objects("content")) == 2
        assert len(store.objects("report")) == 2
    else:
        for hour, minute in ((1, 5), (1, 45), (2, 5), (3, 5), (13, 5)):
            store.claim("simulated-desktop", busy=True)
            tick(store, datetime(2026, 10, 31, hour, minute, tzinfo=UTC))
            tick(store, datetime(2026, 10, 31, hour, minute + 1, tzinfo=UTC))
    from plugins.operations.research import distinct_sources
    assert len(store.objects("source")) == 3
    assert len(distinct_sources(store, "2026-10-31")) == 1
    assert sorted(submissions) == sorted(["comment", "dm", "follow", "publish", "reply"] * (2 if manual else 1))
    report = store.objects("report")[0]["markdown"]
    assert f"已核对成功 {10 if manual else 4} 次" in report
    assert ("confirmed" if manual else "submitted") in report and "https://example.org/result" in report
    # The 21:05 recovery checks only the latest (19:00) interaction slot;
    # duplicate targets are inspected again but never submitted twice.
    assert "不可访问" in report and "模型调用" in report
    assert store.objects("analytics_report") and store.objects("industry_report")
    assert store.objects("content")[0]["analysis_context"]["industry_id"]
    assert "20" in report and "费用未知" in report


def test_unknown_actions_require_explicit_resolution_before_retry(store):
    action = {"kind": "comment", "target": "note", "account_id": "me", "text": "内容"}
    identity = store.reserve_action(action, 1)
    command = store.enqueue("interact", action, identity)
    store.claim("desktop")
    store.acknowledge(command, "desktop", {"state": "unknown"})
    with pytest.raises(ValueError, match="先核对"):
        service.retry_action(store, identity)
    service.resolve_action(store, identity, "confirmed_not_published", "已核对评论列表，没有提交")
    retried = service.retry_action(store, identity)
    assert store.claim("desktop")["id"] == retried
    assert len(store.snapshot()["actions"]) == 1
    assert store.claim("desktop", busy=True) is None


def test_global_pause_blocks_new_reports_and_blocked_capability_requires_new_rules(store):
    command = store.enqueue("inbox", {"kind": "dm", "account_id": "me"})
    store.claim("desktop")
    store.acknowledge(command, "desktop", {"state": "blocked", "error": "需要登录"})
    with pytest.raises(ValueError, match="能力已暂停"):
        store.enqueue("inbox", {"kind": "dm", "account_id": "me"})
    version, policy = store.policy()
    store.configure({**policy, "paused": True}, version)
    tick(store, datetime(2026, 10, 31, 13, 5, tzinfo=UTC))
    assert not store.objects("report")
    assert not store.snapshot()["actions"]


def test_rss_preserves_metadata_and_refuses_entity_expansion():
    from plugins.operations.feeds import parse_feed
    entries = parse_feed(b'<rss><channel><item><title>Walk</title><link>/walk</link><author>Author</author><pubDate>Today</pubDate></item></channel></rss>', "https://example.org/feed")
    assert entries[0] == {"url": "https://example.org/walk", "title": "Walk", "author": "Author", "published_at": "Today"}
    with pytest.raises(ValueError, match="实体"):
        parse_feed(b'<!DOCTYPE test><rss/>', "https://example.org")


def test_schedule_is_idempotent_and_script_runs_in_real_cron_environment(store):
    from cron.jobs import get_job
    from cron.scheduler_script import _run_job_script
    version, policy = store.policy()
    store.configure({**policy, "enabled": False}, version)
    identity = ensure_schedule(store)
    assert ensure_schedule(store) == identity
    job = get_job(identity)
    assert job["no_agent"] is True
    success, output = _run_job_script(job["script"])
    assert success, output
    assert "运营已暂停" in output


def test_follow_rejects_already_followed_and_changed_terms(store):
    action = {"kind": "follow", "account_id": "me", "target": "follower", "item": {"text": "步行爱好者", "follows_me": True, "already_following": True}}
    with pytest.raises(ValueError, match="回关条件"):
        store.reserve_action(action, 1)
    action["item"]["already_following"] = False
    assert store.reserve_action(action, 1)
    command = store.enqueue("interact", action, store.snapshot()["actions"][0]["id"])
    store.claim("desktop")
    store.acknowledge(command, "desktop", {"state": "unknown"})
    with pytest.raises(ValueError, match="未核对"):
        store.reserve_action({**action, "target": "another"}, 1)


def test_lost_execution_lease_cannot_be_renewed_by_previous_owner(store):
    assert store.lease("old")
    with store.connection() as db:
        db.execute("UPDATE leases SET expires=0")
    replacement = Store()
    assert replacement.lease("new")
    with pytest.raises(ValueError, match="租约已过期"):
        store.renew()
    store.release("old")
    replacement.renew()
