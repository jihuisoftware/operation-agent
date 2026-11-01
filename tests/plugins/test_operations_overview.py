"""Overview counts the ledger, not a truncated UI list or unverified outcomes."""
import json

from plugins.operations.overview import overview
from plugins.operations.policy import local_day
from plugins.operations.store import Store


def test_overview_aggregates_all_records_without_exposing_source_bodies(tmp_path):
    store = Store(tmp_path / "operations.db")
    _, policy = store.policy()
    day = local_day(policy)
    for index in range(125):
        store.put("source", {"day": day, "state": "read", "text": "private full body" * 100}, str(index))
    store.put("source", {"day": day, "state": "unavailable"})
    store.put("source", {"day": "2000-01-01", "state": "read"})
    store.put("brief", {"day": day, "result": {"topics": ["old", "duplicate"]}})
    store.put("brief", {"day": day, "result": {"topics": ["new"]}})
    store.put("content", {"day": day, "state": "needs_material"})
    store.put("inbox", {"day": "2000-01-01", "state": "needs_review"})
    store.put("report", {"day": day, "markdown": "long report body"})
    store.event("model_call", {"day": day})
    with store.connection() as db:
        for identity, action_day, kind, state in [
            ("published", day, "publish", "published"),
            ("unknown", day, "publish", "unknown"),
            ("submitted", day, "dm", "submitted"),
            ("replied", day, "reply", "confirmed"),
            ("yesterday", "2000-01-01", "publish", "published"),
        ]:
            db.execute("INSERT INTO actions VALUES (?,?,0,?,?,?,?,?,?)", (
                identity, action_day, kind, identity, state,
                json.dumps({"content": {"title": "已核对的标题"}, "account_id": "test-account"}),
                json.dumps({"url": "https://example.org/note"}), f"{day}T01:00:00+00:00"))
        db.execute("INSERT INTO runs VALUES (?,?, 'research','09:00',0,'failed','采集失败',?,NULL)",
                   ("failed", day, f"{day}T01:00:00+00:00"))
    result = overview(store)
    assert result["counts"] == {"sources": 126, "sources_read": 125, "topics": 1, "content": 1,
                                "published": 1, "interactions": 1, "model_calls": 1}
    assert result["pending"] == {"unverified": 2, "inbox": 1, "content": 1, "failed_today": 1}
    assert [item["id"] for item in result["publications"]] == ["published"]
    assert result["publications"][0]["title"] == "已核对的标题"
    assert result["runs"][0]["state"] == "failed"
    assert result["report"]["day"] == day
    assert "private full body" not in json.dumps(result)
    assert "long report body" not in json.dumps(result)
    assert result["schedule"] == []  # Reading an unconfigured plan never enables it.
    assert not result["online"]
    assert overview(Store(tmp_path / "other.db"))["counts"]["sources"] == 0
