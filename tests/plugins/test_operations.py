"""Business contracts against real SQLite stores and profile scopes; no external account actions."""
from copy import deepcopy
from datetime import datetime, UTC
import json

import pytest

from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.report import daily_report
from plugins.operations.runtime import tick
from plugins.operations.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "operations.db")


def enable(store, **changes):
    version, _ = store.policy()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic="城市步行", goal="整理真实路线", account_id="me", **changes)
    policy["allowed"] = {k: True for k in policy["allowed"]}
    policy["modules"] = {k: True for k in policy["modules"]}
    store.configure(policy, version)
    return version + 1, policy


def action(kind="comment", target="note:1"):
    return {"kind": kind, "target": target, "account_id": "me", "text": "谢谢分享"}


def test_duplicate_claim_quota_and_unknown_results_survive_restart(store):
    version, _policy = enable(store)
    identity = store.reserve_action(action(), version, "2026-10-31")
    assert store.reserve_action(action(), version, "2026-10-31") is None
    command = store.enqueue("interact", action(), identity)
    claimed = store.claim("desktop-a")
    assert claimed["id"] == command
    assert store.claim("desktop-b") is None
    with store.connection() as db:
        db.execute("UPDATE commands SET expires=0 WHERE id=?", (command,))
    restarted = Store(store.path)
    assert restarted.command(command)["state"] == "unknown"
    assert restarted.snapshot()["actions"][0]["state"] == "unknown"
    assert restarted.reserve_action(action(), version, "2026-11-01") is None
    with pytest.raises(ValueError, match="过期"):
        restarted.acknowledge(command, "desktop-a", {"state": "confirmed", "evidence": "late"})


def test_pause_revokes_queued_commands_and_stale_policy(store):
    version, policy = enable(store)
    identity = store.reserve_action(action(), version)
    store.enqueue("interact", action(), identity)
    store.configure({**policy, "paused": True}, version)
    assert store.claim("desktop") is None
    with pytest.raises(ValueError, match="暂停"):
        store.reserve_action(action(target="note:2"), version)
    assert store.snapshot()["actions"][0]["state"] == "cancelled"


def test_limits_are_atomic_and_reset_by_local_date(store):
    limits = {**DEFAULT["limits"], "comment": 1}
    version, policy = enable(store, limits=limits)
    store.reserve_action(action(), version, "2026-10-31")
    with pytest.raises(ValueError, match="额度"):
        store.reserve_action(action(target="note:2"), version, "2026-10-31")
    assert store.reserve_action(action(target="note:2"), version, "2026-11-01")
    assert local_day(policy, datetime(2026, 10, 31, 16, tzinfo=UTC)) == "2026-11-01"


@pytest.mark.parametrize("changes", [{"kind": "dm"}, {"kind": "follow"}, {"account_id": "wrong"}])
def test_uncovered_external_actions_are_refused(store, changes):
    version, _ = enable(store)
    with pytest.raises(ValueError):
        store.reserve_action({**action(), **changes}, version)


def test_worker_cannot_ack_another_worker_or_claim_success_without_evidence(store):
    version, _ = enable(store)
    identity = store.reserve_action(action(), version)
    command = store.enqueue("interact", action(), identity)
    store.claim("a")
    with pytest.raises(ValueError):
        store.acknowledge(command, "b", {"state": "confirmed", "evidence": "yes"})
    store.acknowledge(command, "a", {"state": "confirmed"})
    assert store.snapshot()["actions"][0]["state"] == "unknown"


def test_profile_storage_and_authorization_do_not_leak(tmp_path):
    for name in ("a", "b"):
        token = set_hermes_home_override(str(tmp_path / name))
        try:
            store = Store()
            if name == "a":
                enable(store)
                store.put("task", {"text": "private-a"})
            else:
                assert not store.policy()[1]["enabled"]
                assert store.objects("task") == []
        finally:
            reset_hermes_home_override(token)


def test_cron_occurrences_do_not_repeat_and_missed_publications_are_not_replayed(store, monkeypatch):
    from plugins.operations import workflow
    enable(store)
    calls = []
    monkeypatch.setattr(workflow, "research", lambda *args: calls.append("research"))
    tick(store, datetime(2026, 10, 31, 1, 5, tzinfo=UTC))
    tick(store, datetime(2026, 10, 31, 1, 6, tzinfo=UTC))
    assert calls == ["research"]
    tick(store, datetime(2026, 10, 31, 13, 5, tzinfo=UTC))
    runs = store.snapshot()["runs"]
    assert any(r["stage"] == "publish" and r["state"] == "missed" for r in runs)
    assert store.objects("report")[0]["day"] == "2026-10-31"


def test_report_uses_ledger_and_preserves_missing_metrics(store):
    version, _ = enable(store)
    identity = store.reserve_action(action(), version, "2026-10-31")
    store.put("metric", {"day": "2026-10-31", "name": "阅读", "value": None, "definition": "发布后24小时"}, "batch:1")
    store.put("metric", {"day": "2026-10-31", "name": "阅读", "value": 999}, "batch:1")
    report = daily_report(store, "2026-10-31", delayed=True)["markdown"]
    assert "999" not in report
    assert "费用未知" in report
    assert "延迟补生成：是" in report
    assert "queued" in report and "confirmed" not in report
    assert store.snapshot()["actions"][0]["id"] == identity


def test_real_plugin_registration_exposes_read_only_status_and_cli(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("plugins:\n  enabled: [operations]\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from hermes_cli.plugins import PluginManager
    manager = PluginManager()
    manager.discover_and_load()
    # Use normal discovery/load, so manifest errors and relative imports cannot hide behind fake ctx.
    from tools.registry import registry
    entry = registry.get_entry("operations_status", scope=manager.scope_key)
    assert entry is not None
    result = json.loads(entry.handler({}))
    assert "policy" in result and result["policy"]["enabled"] is False
