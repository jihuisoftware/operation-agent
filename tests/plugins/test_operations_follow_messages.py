"""Followers share intake/receipts while every real follow goes through ordinary admission."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import json

import pytest

from plugins.operations import attention, messages, message_actions, workflow
from plugins.operations.policy import local_day
from plugins.operations.store import Store


@pytest.fixture
def topic(tmp_path):
    store = Store(tmp_path / "topic.db")
    version, policy = store.policy()
    policy.update(
        enabled=True,
        topic="摄影",
        goal="交流",
        account_id="me",
        follow_terms=["摄影"],
        receive={"reply": False, "dm": False, "follow": True},
    )
    policy["allowed"]["follow"] = policy["modules"]["follow"] = True
    version = store.configure(policy, version)
    store.claim("desktop", busy=True)
    return store, policy, version


def observed(target="fan", **other):
    return {"id": target, "text": "摄影爱好者", "follows_me": True, "already_following": False, **other}


def test_receive_only_detects_followers_and_preserves_ignores(topic, monkeypatch):
    store, p, v = topic
    p["allowed"]["follow"] = False
    v = store.configure(p, v)
    items = [observed(), observed("mutual", already_following=True), observed("not-a-fan", follows_me=False)]
    calls = []
    monkeypatch.setattr(
        workflow, "browser", lambda _, op, payload: calls.append((op, payload["kind"])) or {"items": items}
    )
    monkeypatch.setattr(workflow, "generate", lambda *_: pytest.fail("receive-only must not call a model"))
    for _ in range(2):
        workflow.interact(store, p, local_day(p), v, kinds=("follow",))
    rows = {r["target"]: r for r in messages.listing(store, kind="follow")["items"]}
    assert {k: r["state"] for k, r in rows.items()} == {"fan": "manual", "mutual": "followed"}
    row = messages.detail(store, rows["fan"]["id"])
    assert row["matching_terms"] == ["摄影"] and row["follow_disabled_reason"]
    with pytest.raises(ValueError):
        message_actions.change(store, row["id"], {"revision": row["revision"], "operation": "follow"})
    req = {"revision": row["revision"], "operation": "ignore"}
    assert message_actions.change(store, row["id"], req) == message_actions.change(store, row["id"], req)
    p["allowed"]["follow"] = True
    v = store.configure(p, v)
    workflow.interact(store, p, local_day(p), v, kinds=("follow",))
    assert messages.detail(store, row["id"])["state"] == "ignored"
    assert calls == [("inbox", "follow")] * 3 and not store.snapshot()["actions"]


def test_operator_and_scheduler_share_one_action_and_receipt(topic):
    store, p, v = topic
    fan = observed()
    messages.read_items(store, "follow", "me", [fan], auto=True, day=local_day(p))
    (row,) = messages.listing(store)["items"]
    barrier = Barrier(2)

    def human():
        barrier.wait(timeout=5)
        try:
            return message_actions.change(
                store, row["id"], {"operation": "follow", "revision": row["revision"]}
            )
        except messages.Conflict:
            return None

    def automatic():
        barrier.wait(timeout=5)
        return store.reserve_action({"kind": "follow", "account_id": "me", "target": fan["id"], "item": fan}, v)

    with ThreadPoolExecutor(2) as pool:
        x, y = pool.submit(human), pool.submit(automatic)
        human_result, auto_result = x.result(), y.result()
    assert bool(human_result) != bool(auto_result)
    cmd = store.claim("desktop")
    assert cmd and cmd["kind"] == "interact"
    store.acknowledge(cmd["id"], "desktop", {"state": "unknown", "evidence": "暂未确认"})
    updated = messages.detail(store, row["id"])
    assert updated["state"] == "verify"
    (pending,) = attention.listing(store, "unverified")["items"]
    assert pending["origin"] == {"tab": "messages", "source": "follow", "record": row["id"]}
    from plugins.operations.service import resolve_action

    resolve_action(store, updated["action_id"], "confirmed", "平台显示互相关注")
    assert not attention.listing(store, "unverified")["total"]
    assert messages.detail(store, row["id"])["state"] == "followed"
    assert len(store.snapshot()["actions"]) == 1


def test_operator_follow_obeys_terms_quota_and_stale_revision(topic):
    store, p, v = topic
    messages.read_items(
        store,
        "follow",
        "me",
        [observed(), observed("b"), observed("c", text="其他")],
        auto=False,
        day=local_day(p),
    )
    rows = {r["target"]: r for r in messages.listing(store)["items"]}

    def request(r):
        return message_actions.change(store, r["id"], {"operation": "follow", "revision": r["revision"]})

    with pytest.raises(ValueError, match="条件"):
        request(rows["c"])
    p["limits"]["follow"] = 1
    store.configure(p, v)
    assert request(rows["fan"]) == request(rows["fan"])
    with pytest.raises(ValueError, match="额度"):
        request(rows["b"])
    assert len(store.snapshot()["actions"]) == 1


def test_upgrades_preexisting_message_table_once_without_queueing(topic):
    store, p, _ = topic
    messages.read_items(store, "reply", "me", [{"id": "r", "text": "保留我"}], auto=False, day=local_day(p))
    with store.connection() as db:
        db.execute("DROP TABLE inbound_follow_import")
    for id in ("old-a", "old-b"):
        store.put("inbox", {**observed(), "account_id": "me", "kind": "follow", "state": "needs_review"}, id)
    store.put("inbox", {"kind": "follow", "text": "历史关注"}, "unmatched")
    for _ in range(2):
        page = messages.listing(store)
        assert page["total"] == 3
    joined = next(r for r in page["items"] if r["target"] == "fan")
    assert len(messages.detail(store, joined["id"])["history"]) == 2
    assert any(r["state"] == "archived" for r in page["items"])
    assert not store.snapshot()["actions"]


def test_review_origins_include_scoped_business_records_and_keep_raw_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    store = Store()
    messages.initialize(store)
    with store.connection() as db:
        for kind, identity, data in [
            ("publish", "p", {"content": {"id": "draft", "title": "标题"}}),
            ("comment", "c", {"target": "note:1"}),
            ("reply", "unlinked", {}),
        ]:
            db.execute(
                "INSERT INTO actions VALUES(?,?,1,?,?,'submitted',?,?,?)",
                (identity, "2026-11-25", kind, identity, json.dumps(data), '{"evidence":"回执"}', "2026-11-25"),
            )
    rows = {r["id"]: r for r in attention.listing(store, "unverified")["items"]}
    assert rows["p"]["origin"]["record"] == "p" and rows["p"]["origin"]["tab"] == "published"
    assert rows["c"]["origin"]["record"] == "c" and rows["c"]["origin"]["topic_id"] == store.scope["id"]
    assert "origin" not in rows["unlinked"] and rows["unlinked"]["evidence"] == "回执"
    assert attention.listing(store, "unverified", record="p")["total"] == 1


@pytest.mark.parametrize('kind',['reply','dm'])
def test_review_links_to_original_message_with_its_action_evidence(tmp_path, kind):
    store = Store(tmp_path/'origin.db')
    data = {'kind':kind, 'target':'platform-id', 'account_id':'me','inbound':True,
            'item':{'id':'platform-id','inbound':True,'text':'原文'}}
    with store.connection() as db:
        for identity in ('a','b'):
            db.execute("INSERT INTO actions VALUES(?,?,1,?,?,'unknown',?,?,?)",
                       (identity,'2026-11-24',kind,identity,json.dumps(data),'{}','2026-11-24'))
        db.execute("INSERT INTO objects VALUES('submit-step','browser_step',?,'2026-11-25T10:00:00Z')",
                   (json.dumps({'action_id':'a','name':'submit_interaction','phase':'completed'}),))
    rows = {r['id']:r for r in attention.listing(store,'unverified')['items']}
    assert rows['a']['origin']==rows['b']['origin']
    assert rows['a']['submitted_at']=='2026-11-25T10:00:00Z'
    assert rows['b']['submitted_at'] is None
    msg = messages.detail(store,rows['a']['origin']['record'])
    assert msg['state']=='verify' and msg['kind']==kind
