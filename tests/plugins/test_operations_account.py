"""Follow the embedded login without configuring an account or trusting cached evidence."""
from copy import deepcopy
import json

import pytest

from plugins.operations import blueprints, workflow
from plugins.operations.policy import DEFAULT
from plugins.operations.store import Store


def test_current_login_is_resolved_per_stage_and_recorded_without_changing_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    store = Store(tmp_path / "operations.db")
    policy = deepcopy(DEFAULT)
    policy.update(topic="路线", goal="回答开放时间", knowledge=["每天九点开放"])
    policy["modules"]["dm"] = True
    body = {"version": 0, "policy": policy, "mode": "enable", "request_id": "auto-account"}
    assert blueprints.preview(store, body)["missing"] == {}
    blueprints.apply(store, body)
    version, policy = store.policy()
    monkeypatch.setattr(workflow, "generate", lambda *args: {
        "actions": [{"id": "message", "text": "每天九点开放", "knowledge_ids": [0]}]})
    active = {"account": "first"}
    original = store.command
    commands = []

    def consume(identity):
        command = store.claim("desktop")
        assert command["id"] == identity
        commands.append(command)
        if command["kind"] == "account":
            result = {"account_id": active["account"]}
        elif command["kind"] == "inbox":
            assert command["payload"]["account_id"] == active["account"]
            result = {"items": [{"id": "message", "text": "开放时间？", "inbound": True}]}
        else:
            assert command["payload"]["account_id"] == active["account"]
            result = {"state": "confirmed", "evidence": "模拟消息回执"}
        store.acknowledge(identity, "desktop", result)
        return original(identity)

    monkeypatch.setattr(store, "command", consume)
    for account in ("first", "first", "second"):
        active["account"] = account
        workflow.interact(store, policy, "2026-10-31", version, kinds=("dm",))
    actions = store.snapshot()["actions"]
    assert {json.loads(a["data"])["account_id"] for a in actions} == {"first", "second"}
    assert len(actions) == 2
    assert {item["account_id"] for item in store.objects("inbox")} == {"first", "second"}
    assert sum(c["kind"] == "account" for c in commands) == 3
    assert store.policy() == (version, policy)
    assert policy["account_id"] == ""


def test_missing_live_identity_cannot_reserve_or_send_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    store = Store(tmp_path / "operations.db")
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic="路线", goal="回复评论")
    policy["modules"]["comments"] = True
    store.configure(policy, 0)
    monkeypatch.setattr(workflow, "browser", lambda *args, **kwargs: {"account_id": ""})
    with pytest.raises(ValueError, match="扫码登录"):
        workflow.interact(store, policy, "2026-10-31", 1, kinds=("reply",))
    with pytest.raises(ValueError, match="识别"):
        store.reserve_action({"kind": "reply", "account_id": "", "target": "message"}, 1)
    assert not store.snapshot()["actions"]


@pytest.mark.parametrize("manual", [False, True])
def test_legacy_action_ids_still_deduplicate_with_account_scoped_targets(tmp_path, monkeypatch, manual):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    store = Store(tmp_path / "operations.db")
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic="路线", goal="回复评论")
    policy["modules"]["comments"] = True
    store.configure(policy, 0)
    store.manual_run_id = "batch" if manual else None
    action = {"kind": "reply", "account_id": "first", "target": "message"}
    identity = store.reserve_action(action, 1)
    with store.connection() as db:
        db.execute("UPDATE actions SET id='legacy', target=?, state='confirmed' WHERE id=?",
                   ("manual:batch:message" if manual else "message", identity))
    assert store.reserve_action(action, 1) is None
    assert store.reserve_action({**action, "account_id": "second"}, 1)
    assert {a["id"] for a in store.snapshot()["actions"]} >= {"legacy"}
    assert len(store.snapshot()["actions"]) == 2
