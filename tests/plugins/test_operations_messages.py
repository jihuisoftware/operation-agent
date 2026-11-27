"""Message intake, local handling, shared ownership and delivery receipts."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from plugins.operations import attention, message_actions, messages, workflow
from plugins.operations.policy import local_day
from plugins.operations.store import Store
from tests.plugins.test_operations_workspace_accounts import account_topics


def configured(store, kind, *, send=True):
    version, p = store.policy()
    p.update(
        topic="路线",
        goal="答疑",
        account_id="me",
        enabled=True,
        knowledge=["九点开放"],
        receive={"reply": kind == "reply", "dm": kind == "dm"},
    )
    p["modules"]["dm" if kind == "dm" else "comments"] = True
    p["allowed"][kind] = send
    version = store.configure(p, version)
    return p, version


def scan(store, kind, p, version):
    return workflow.interact(store, p, local_day(p), version, kinds=(kind,))


def test_inbound_only_without_model_then_handle_blocks_manual_batch(tmp_path, monkeypatch):
    store = Store(tmp_path / "topic.db")
    p, v = configured(store, "dm", send=False)
    entries = [
        {"id": "m", "inbound": True, "text": "问题"},
        {"id": "out", "inbound": False},
        {"text": "缺少标识"},
    ]
    calls = []
    monkeypatch.setattr(
        workflow, "browser", lambda _, operation, payload: calls.append(operation) or {"items": entries}
    )
    monkeypatch.setattr(workflow, "generate", lambda *_: pytest.fail("只收不发或已办结不应调用模型"))
    scan(store, "dm", p, v)
    scan(store, "dm", p, v)
    (row,) = messages.listing(store, state="attention")["items"]
    assert calls == ["inbox", "inbox"] and row["state"] == "manual" and row["target"] == "m"
    req = {"operation": "take", "revision": row["revision"]}
    assert message_actions.change(store, row["id"], req) == message_actions.change(store, row["id"], req)
    with pytest.raises(messages.Conflict):
        message_actions.change(store, row["id"], {"operation": "handle", "revision": row["revision"]})
    current = messages.detail(store, row["id"])
    message_actions.change(store, row["id"], {"operation": "handle", "revision": current["revision"]})
    p, v = configured(store, "dm")
    store.manual_run_id = "manual-repeat"
    scan(store, "dm", p, v)
    assert messages.listing(store)["items"][0]["state"] == "handled"
    assert not store.snapshot()["actions"]
    p["receive"]["dm"] = False
    v = store.configure(p, v)
    from plugins.operations.outcomes import StageSkipped

    with pytest.raises(StageSkipped):
        scan(store, "dm", p, v)
    assert len(calls) == 3


def test_risky_and_unsupported_dm_both_visible_once(tmp_path, monkeypatch):
    store = Store(tmp_path / "topic.db")
    p, v = configured(store, "dm")
    entries = [
        {"id": "refund", "text": "退款", "inbound": True},
        {"id": "hours", "text": "几点开门", "inbound": True},
    ]
    monkeypatch.setattr(workflow, "browser", lambda *_: {"items": entries})
    monkeypatch.setattr(
        workflow, "generate", lambda *_: {"actions": [{"id": "hours", "text": "通宵", "knowledge_ids": [0]}]}
    )
    for _ in range(2):
        scan(store, "dm", p, v)
    page = messages.listing(store, state="attention")
    assert page["total"] == 2
    assert {row["reason"] for row in page["items"]} == {
        "交易承诺、争议或敏感资料需人工处理",
        "私信回复超出已确认知识，需人工处理",
    }
    assert attention.listing(store, "inbox")["total"] == 2 and not store.snapshot()["actions"]


def test_two_topics_one_owner_and_transfer_never_sends(tmp_path):
    _, stores = account_topics(tmp_path)
    barrier = Barrier(2)
    item = {"id": "platform:42", "text": "问题"}

    def receive(store):
        barrier.wait(timeout=5)
        messages.read_items(store, "reply", "me", [item], auto=True, day="2026-11-26")

    with ThreadPoolExecutor(2) as pool:
        list(pool.map(receive, stores))
    source, destination = sorted(stores, key=lambda s: messages.listing(s)["total"], reverse=True)
    (row,) = messages.listing(source)["items"]
    assert not messages.listing(destination)["total"]
    req = {"operation": "transfer", "revision": row["revision"], "target_topic": destination.scope["id"]}
    assert message_actions.change(source, row["id"], req) == message_actions.change(source, row["id"], req)
    for store in stores:
        assert not messages.read_items(store, "reply", "me", [item], auto=True, day="2026-11-26")
        assert not store.snapshot()["actions"]
    moved = messages.detail(destination, row["id"])
    assert moved["state"] == "manual" and moved["history"][-1]["request"]["from"] == source.scope["id"]


def test_pending_model_retry_and_action_receipt_fence(tmp_path, monkeypatch):
    store = Store(tmp_path / "topic.db")
    p, v = configured(store, "reply")
    entry = {"id": "r", "text": "几点开放"}

    def browser(store, kind, payload, action_id=None):
        if kind == "inbox":
            return {"items": [entry]}
        cmd = store.claim("test")
        assert cmd["kind"] == "interact" and cmd["payload"]["target"] == "r"
        store.acknowledge(cmd["id"], "test", {"state": "unknown", "evidence": "提交后断线"})
        return {"state": "unknown"}

    monkeypatch.setattr(workflow, "browser", browser)

    def offline(*_):
        raise TimeoutError("模拟模型超时")

    monkeypatch.setattr(workflow, "generate", offline)
    with pytest.raises(TimeoutError):
        scan(store, "reply", p, v)
    (row,) = messages.listing(store)["items"]
    assert row["state"] == "auto"
    monkeypatch.setattr(workflow, "generate", lambda *_: {"actions": [{"id": "r", "text": "九点开放"}]})
    scan(store, "reply", p, v)
    result = messages.detail(store, row["id"])
    assert result["state"] == "verify" and result["receipt"]["evidence"] == "提交后断线"
    with pytest.raises(messages.Conflict):
        message_actions.change(store, row["id"], {"revision": row["revision"], "operation": "take"})
    store.manual_run_id = "retry"
    scan(store, "reply", p, v)
    assert len(store.snapshot()["actions"]) == 1


def test_legacy_duplicate_never_reopens_on_scan(tmp_path):
    store = Store(tmp_path / "topic.db")
    row = {"kind": "dm", "id": "m", "account_id": "me", "text": "退款", "inbound": True}
    store.put("inbox", {**row, "state": "proposed"}, "me:dm:m")
    store.put("inbox", {**row, "state": "needs_review", "reason": "需要客服"}, "random")
    store.put("inbox", {**row, "state": "handled"}, "finished")
    store.put("inbox", {"kind": "dm", "state": "needs_review", "text": "无法匹配"}, "old")
    page = messages.listing(store)
    assert page["total"] == 2
    assert {r["state"] for r in page["items"]} == {"handled", "archived"}
    assert not messages.read_items(store, "dm", "me", [row], auto=True, day="2026-11-26")
    joined = next(r for r in page["items"] if r["state"] == "handled")
    assert len(messages.detail(store, joined["id"])["history"]) == 3


def test_take_and_send_are_mutually_exclusive(tmp_path):
    store = Store(tmp_path / "race.db")
    policy, version = configured(store, "reply")
    day = local_day(policy)
    item = {"id": "incoming", "text": "问题"}
    messages.read_items(store, "reply", "me", [item], auto=True, day=day)
    (row,) = messages.listing(store)["items"]
    barrier = Barrier(2)

    def take():
        barrier.wait(timeout=5)
        try:
            return message_actions.change(store, row["id"], {"revision": row["revision"], "operation": "take"})[
                "ok"
            ]
        except messages.Conflict:
            return False

    def send():
        barrier.wait(timeout=5)
        action = {"kind": "reply", "account_id": "me", "target": item["id"], "item": item, "text": "九点开放"}
        return bool(store.reserve_action(action, version, day))

    with ThreadPoolExecutor(2) as pool:
        first, second = pool.submit(take), pool.submit(send)
        taken, sent = first.result(), second.result()
    assert taken != sent
    assert messages.detail(store, row["id"])["state"] == ("working" if taken else "sending")
    assert len(store.snapshot()["actions"]) == int(sent)


def test_quota_defers_messages_and_confirmed_receipt_ends_reply(tmp_path, monkeypatch):
    store = Store(tmp_path / "quota.db")
    p, v = configured(store, "reply")
    p["limits"]["reply"] = 1
    v = store.configure(p, v)
    entries = [{"id": "a", "text": "问题一"}, {"id": "b", "text": "问题二"}]

    def browser(store, operation, payload, action_id=None):
        if operation == "inbox":
            return {"items": entries}
        cmd = store.claim("desktop")
        result = {"state": "confirmed", "evidence": "平台显示新增回复"}
        store.acknowledge(cmd["id"], "desktop", result)
        return result

    monkeypatch.setattr(workflow, "browser", browser)
    monkeypatch.setattr(
        workflow,
        "generate",
        lambda *_: {"actions": [{"id": item["id"], "text": "九点开放"} for item in entries]},
    )
    scan(store, "reply", p, v)
    assert {r["target"]: r["state"] for r in messages.listing(store)["items"]} == {"a": "replied", "b": "auto"}
    monkeypatch.setattr(workflow, "generate", lambda *_: pytest.fail("额度用尽时不应重复生成"))
    scan(store, "reply", p, v)
    assert len(store.snapshot()["actions"]) == 1


def test_api_filters_and_conflicts_are_scoped(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from hermes_cli import web_server

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    store = Store()
    item = {"id": "abc", "text": "你好"}
    messages.read_items(store, "reply", "acct", [item], auto=False, day="2026-11-26")
    params = {"business_id": store.scope["business_id"], "topic_id": store.scope["id"]}
    other = store.workspace.create("其他业务")
    url = "/api/plugins/operations/messages"
    with TestClient(web_server.app) as client:
        assert client.get(url, params=params).status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        page = client.get(url, params={**params, "state": "attention", "source": "reply"}).json()
        assert (
            page["total"]
            == client.get("/api/plugins/operations/overview", params=params).json()["pending"]["inbox"]
            == 1
        )
        row = page["items"][0]
        assert client.get(url + "/" + row["id"], params=other).status_code == 404
        req = {"operation": "take", "revision": row["revision"]}
        assert client.post(url + "/" + row["id"], params=params, json=req).status_code == 200
        assert (
            client.post(url + "/" + row["id"], params=params, json={**req, "operation": "handle"}).status_code
            == 409
        )
        assert client.get(url, params={**params, "state": "working"}).json()["total"] == 1


def test_pending_message_retried_after_leaving_viewport_without_blind_send(tmp_path, monkeypatch):
    store = Store(tmp_path / "retry.db")
    policy, version = configured(store, "reply")
    messages.read_items(store, "reply", "me", [{"id": "m", "text": "原文"}], auto=True, day=local_day(policy))
    monkeypatch.setattr(
        workflow,
        "browser",
        lambda store, kind, payload: {"items": []} if kind == "inbox" else pytest.fail("目标不在页面"),
    )
    seen = []

    def propose(store, p, day, prompt, data):
        seen.extend(item["id"] for item in data["candidates"])
        return {"actions": [{"id": "m", "text": "九点开放"}]}

    monkeypatch.setattr(workflow, "generate", propose)
    scan(store, "reply", policy, version)
    (row,) = messages.listing(store, state="attention")["items"]
    assert seen == ["m"] and "重新定位" in row["reason"] and not store.snapshot()["actions"]


def test_message_api_shares_reads_by_bound_account_but_keeps_handling_with_owner(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from hermes_cli import web_server

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    source = Store()
    directory = source.workspace
    origin = {"business_id": source.scope["business_id"], "topic_id": source.scope["id"]}
    peer = directory.create("第二个主题", business=origin["business_id"])
    other = directory.create("独立业务")
    with directory.connection() as db:
        db.execute("UPDATE accounts SET identity='acct' WHERE id=?", (source.scope["account"],))
    messages.read_items(source, "dm", "acct", [{"id": "m", "text": "几点开门", "inbound": True}], auto=False, day="2026-11-27")
    url = "/api/plugins/operations/messages"
    with TestClient(web_server.app) as client:
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        page = client.get(url, params={**peer, "source": "dm", "state": "attention"}).json()
        assert page["total"] == 1
        row, = page["items"]
        path = url + "/" + row["id"]
        detail = client.get(path, params=peer).json()
        assert detail["text"] == "几点开门" and detail["owner_topic"] == source.scope["name"]
        assert detail["read_only"] and not client.get(path, params=origin).json()["read_only"]
        assert client.post(path, params=peer, json={"revision": row["revision"], "operation": "take"}).status_code == 404
        assert client.get(url, params=other).json()["total"] == 0
        assert client.get(path, params=other).status_code == 404
        with directory.connection() as db:
            db.execute("UPDATE accounts SET identity='replacement' WHERE id=?", (source.scope["account"],))
        assert client.get(path, params=peer).status_code == 404
        assert client.get(url, params=peer).json()["total"] == 0
