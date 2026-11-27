"""Daily work claims survive a second invocation, changing evidence and rollovers."""

from datetime import datetime
import json
from zoneinfo import ZoneInfo

from plugins.operations import daily_tasks, runtime, topics
from plugins.operations.store import Store


def at(day, clock):
    return datetime.fromisoformat(day + "T" + clock).replace(tzinfo=ZoneInfo("Asia/Shanghai"))


def configured(tmp_path):
    store = Store(tmp_path / "daily.db")
    _, policy = store.policy()
    policy.update(topic="工具", goal="每日分享", enabled=True, draft_goal=2)
    policy["modules"] = {k: k in ("content", "topics") for k in policy["modules"]}
    store.configure(policy, 0)
    return store, store.policy()[1]


def test_afternoon_resume_waits_for_new_topics_and_next_day_has_own_target(tmp_path, monkeypatch):
    store, policy = configured(tmp_path)
    day = "2026-11-27"
    store.put(
        "brief",
        {
            "day": day,
            "scope_topic": policy["topic"],
            "source_ids": ["s"],
            "result": {"topics": [{"title": "第一篇", "source_ids": ["s"]}]},
        },
        "first",
    )
    monkeypatch.setattr(runtime.workflow, "research", lambda *args: None)
    monkeypatch.setattr("plugins.operations.workflow.produce", write_draft)
    monkeypatch.setattr("plugins.operations.topics.generate_topics", lambda *args: "已有选题")
    runtime.tick(store, at(day, "14:00"))
    assert daily_tasks.today(store, at(day, "14:00"))["completed"] == 1
    reopened = Store(store.path)
    runtime.tick(reopened, at(day, "14:10"))
    assert len(reopened.objects("content")) == 1
    assert daily_tasks.today(reopened, at(day, "14:10"))["waiting_topic"]
    reopened.put(
        "topic_selection",
        {"day": day, "scope_topic": policy["topic"], "origin": "manual", "title": "第二篇", "source_ids": []},
    )
    runtime.tick(reopened, at(day, "15:00"))
    assert len(reopened.objects("content")) == daily_tasks.today(reopened, at(day, "15:00"))["completed"] == 2
    assert not list(daily_tasks.available(reopened, policy, at(day, "22:30")))
    assert daily_tasks.today(reopened, at("2026-11-28", "12:00"))["completed"] == 0


def write_draft(store, policy, day, version):
    topic = topics.production_topic(store, policy, day)
    key = store.put(
        "content",
        {
            "day": day,
            "state": "pending_review",
            "review_pending": False,
            "ready": True,
            "title": topic["title"],
            "selected_topic": topic,
            "production_input": "fixture",
        },
    )
    return {"content_id": key, "ready": True}


def test_poll_uses_current_window_and_outreach_has_one_daily_claim(tmp_path):
    store, policy = configured(tmp_path)
    policy["modules"].update(comments=True, dm=True, follow=True)
    policy["receive"] = {"reply": True, "dm": True, "follow": True}
    tuples = lambda clock: [
        (stage, slot) for _, stage, slot in daily_tasks.available(store, policy, at("2026-11-27", clock))
    ]
    assert not tuples("07:59")
    morning = tuples("08:07")
    assert ("dm", "poll:08:00") in morning and ("follow", "poll:08:00") in morning
    run = store.start_run("2026-11-27", "comments", "daily:outreach", 1)
    store.finish_run(run, "completed", "已检查")
    afternoon = tuples("15:12")
    assert ("dm", "poll:15:00") in afternoon and ("comments", "daily:outreach") not in afternoon
    assert not any(slot == "poll:08:30" for _, slot in afternoon)


def test_draft_goal_counts_a_reviewed_root_once_and_excludes_debug_lineage(tmp_path):
    store, _ = configured(tmp_path)
    day = "2026-11-27"
    data = {
        "day": day,
        "production_input": "evidence",
        "title": "独立稿件",
        "ready": True,
        "state": "pending_review",
    }
    store.put("content", data, "root")
    store.put("content", {**data, "revision_root_id": "root"}, "child")
    store.put("content", {**data, "debug_id": "debug:one"}, "debug-root")
    store.put("content", {**data, "revision_root_id": "debug-root"}, "debug-child")
    assert daily_tasks.today(store, at(day, "14:00"))["completed"] == 1


def test_late_publication_receipt_is_visible_on_the_observed_day(tmp_path):
    from plugins.operations.daily_receipts import markdown, record
    from plugins.operations.policy import local_day

    store, policy = configured(tmp_path)
    with store.connection() as db:
        db.execute(
            "INSERT INTO actions(id,day,version,kind,target,state,data,result,created) VALUES ('a','2020-01-01',1,'publish','target','published',?,'{}',?)",
            (json.dumps({"content": {"title": "昨日排期的稿件"}}), "2020-01-01T00:00:00+00:00"),
        )
        record(db, {"kind": "publish", "id": "cmd", "action_id": "a"})
        report = {"day": local_day(policy), "created": "2020-01-02T00:00:00+00:00"}
        assert "昨日排期的稿件 · 已发布" in markdown(db, report, "今日小结")
        assert markdown(db, {**report, "day": "2020-01-01"}, "昨日小结") == "昨日小结"
