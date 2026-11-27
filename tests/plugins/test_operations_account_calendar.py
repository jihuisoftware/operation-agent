"""Concurrent reviews reserve shared-account slots in the same transaction as the release."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, UTC
import json

from plugins.operations import account_calendar as calendar
from plugins.operations.store import encoded
from plugins.operations.workspaces import Workspaces


def book(store, identity, now):
    _, policy = store.policy()
    policy.update(enabled=True, paused=False)
    policy["modules"] = {**policy["modules"], "publish": True}
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        release = {
            "content_id": identity,
            "account_scope": calendar.account_key(store, db),
            "reviewed_at": now.isoformat(),
            "revision": 1,
        }
        calendar.assign(store, db, policy, now, release)
        db.execute(
            "INSERT INTO objects VALUES (?, 'content_release', ?, ?)",
            ("content-release:" + identity, encoded(release), now.isoformat()),
        )
        return release


def test_cross_topic_claims_and_legacy_appointment(tmp_path):
    directory = Workspaces(tmp_path)
    first = directory.store()
    second = directory.store(
        first.scope["business_id"],
        directory.create("第二主题", business=first.scope["business_id"])["topic_id"],
    )
    now = datetime(2026, 11, 27, 0, 0, tzinfo=UTC)
    first.put(
        "content_release",
        {
            "content_id": "legacy",
            "state": "scheduled",
            "publish_at": "2026-11-27T02:00:00+00:00",
            "account_scope": first.scope["account"],
            "reviewed_at": now.isoformat(),
        },
        "content-release:legacy",
    )
    with ThreadPoolExecutor(2) as pool:
        releases = list(pool.map(lambda pair: book(*pair, now), [(first, "a"), (second, "b")]))
    assert sorted(r["publish_at"] for r in releases) == [
        "2026-11-28T02:00:00+00:00",
        "2026-11-29T02:00:00+00:00",
    ]


def test_zero_capacity_records_approval_then_schedules_on_resume(tmp_path):
    store = Workspaces(tmp_path).store()
    _, policy = store.policy()
    policy.update(topic="主题", goal="发稿", enabled=True, modules={**policy["modules"], "publish": True})
    store.configure(policy, 0)
    now = datetime(2026, 11, 27, 0, 0, tzinfo=UTC)
    setting = calendar.configure(
        store,
        {
            "account": store.scope["account"],
            "revision": 0,
            "timezone": "Asia/Shanghai",
            "limit": 0,
            "slots": ["10:00"],
        },
    )
    assert book(store, "a", now)["state"] == "waiting_slot"
    calendar.configure(store, {**setting, "limit": 1})
    calendar.drain(store, now)
    assert store.objects("content_release")[0]["publish_at"] == "2026-11-27T02:00:00+00:00"
