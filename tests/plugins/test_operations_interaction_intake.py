"""Receive the due sources before planning or submitting any interaction."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from plugins.operations import messages, workflow
from plugins.operations.execution_pause import ExecutionPaused
from plugins.operations.store import Store


@pytest.fixture
def engagement(tmp_path, monkeypatch):
    store = Store(tmp_path / "topic.db")
    version, policy = store.policy()
    policy.update(
        topic="互动",
        goal="回复",
        account_id="me",
        enabled=True,
        knowledge=["九点开放"],
        receive={"reply": True, "dm": True},
    )
    policy["modules"].update(comments=True, dm=True)
    policy["allowed"].update(comment=True, reply=True, dm=True)
    version = store.configure(policy, version)
    now = datetime.now(ZoneInfo(policy["timezone"])).replace(hour=15, minute=2)
    store.execution_now = now
    day = now.date().isoformat()
    # Both sources were enabled before today's first scheduled slot.
    with store.connection() as db:
        db.execute("UPDATE events SET at=? WHERE kind='policy'", (day + "T00:00:00+08:00",))
    calls = []

    def browser(owner, operation, payload, action_id=None):
        kind = payload["kind"]
        calls.append((operation, kind))
        if operation == "inbox":
            return {"items": [{"id": kind, "text": "几点开放", "inbound": kind == "dm"}]}
        assert operation == "interact"
        return {"state": "confirmed", "evidence": "模拟回执"}

    def model(owner, p, when, prompt, data):
        kind = data["kind"]
        calls.append(("model", kind))
        return {"actions": [{"id": kind, "text": "九点开放", "knowledge_ids": [0]}]}

    monkeypatch.setattr(workflow, "browser", browser)
    monkeypatch.setattr(workflow, "generate", model)
    return store, policy, version, day, calls


@pytest.mark.parametrize("slot", ["15:00", "manual:batch"])
def test_all_intake_committed_before_outbound_and_reused_on_next_tick(engagement, monkeypatch, slot):
    store, policy, version, day, calls = engagement
    original = workflow.browser

    def pause_on_comment(owner, operation, payload, action_id=None):
        if operation == "interact" and payload["kind"] == "comment":
            assert {row["kind"] for row in messages.listing(owner)["items"]} == {"reply", "dm"}
            raise ExecutionPaused({"error": "主动评论输入框不可用"})
        return original(owner, operation, payload, action_id)

    monkeypatch.setattr(workflow, "browser", pause_on_comment)
    run = store.start_run(day, "comments", slot, version)
    with pytest.raises(ExecutionPaused):
        workflow.interact(store, policy, day, version, kinds=("comment", "reply"))
    assert calls[:3] == [("inbox", "reply"), ("inbox", "dm"), ("inbox", "comment")]
    store.finish_run(run, "paused", "主动评论暂停")
    reopened = Store(store.path)
    reopened.execution_now = store.execution_now
    reopened.start_run(day, "dm", slot, version)
    workflow.interact(reopened, policy, day, version, kinds=("dm",))
    assert calls.count(("inbox", "dm")) == 1
    assert ("interact", "dm") in calls


@pytest.mark.parametrize("mode", ["cancelled", "later", "disabled"])
def test_unselected_sources_are_not_prefetched(engagement, mode):
    store, policy, version, day, calls = engagement
    if mode == "cancelled":
        run = store.start_run(day, "dm", "15:00", version)
        store.finish_run(run, "cancelled", "人工取消")
    elif mode == "later":
        policy["times"]["dm"] = ["19:00"]
    else:
        policy["receive"]["dm"] = False
    store.start_run(day, "comments", "15:00", version)
    workflow.interact(store, policy, day, version, kinds=("comment", "reply"))
    assert calls[:2] == [("inbox", "reply"), ("inbox", "comment")]
    assert ("inbox", "dm") not in calls


def test_failed_read_keeps_other_inbox_and_blocks_every_send(engagement, monkeypatch):
    store, policy, version, day, calls = engagement
    original = workflow.browser

    def fail(owner, operation, payload, action_id=None):
        if payload["kind"] == "reply":
            calls.append((operation, "reply"))
            raise ValueError("未识别到评论列表")
        return original(owner, operation, payload, action_id)

    monkeypatch.setattr(workflow, "browser", fail)
    for stage, kinds in [("comments", ("comment", "reply")), ("dm", ("dm",))]:
        run = store.start_run(day, stage, "15:00", version)
        with pytest.raises(ValueError, match="收件未完成"):
            workflow.interact(store, policy, day, version, kinds=kinds)
        store.finish_run(run, "failed", "收件未完成")
    assert calls == [("inbox", "reply"), ("inbox", "dm"), ("inbox", "reply")]
    assert messages.listing(store)["items"][0]["kind"] == "dm"
    assert not store.snapshot()["actions"]


def test_scheduled_tick_reads_both_sources_then_dispatches_only_one_stage(engagement, monkeypatch):
    from plugins.operations import readiness, runtime

    store, policy, _, _, calls = engagement
    now = store.execution_now
    monkeypatch.setattr(store, "online", lambda: True)
    monkeypatch.setattr(readiness, "refresh", lambda *args: {s: {"ready": True} for s in policy["modules"]})
    runtime.tick(store, now, scheduled=True)
    assert calls == [('inbox','reply'), ('inbox','dm'), ('model','reply'), ('interact','reply')]
    runtime.tick(store, now, scheduled=True)
    runtime.tick(store, now, scheduled=True)
    assert calls.count(('inbox','dm')) == 1
    assert calls.count(('interact','dm')) == calls.count(('interact','comment')) == 1
    with store.connection() as db:
        assert {tuple(r) for r in db.execute('SELECT stage,slot,state FROM runs')} == {
            ('comments','poll:15:00','completed'), ('dm','poll:15:00','completed'), ('comments','daily:outreach','completed')
        }


@pytest.mark.parametrize(
    "selected,expected",
    [(["comment"], []), (["comment", "dm"], ["dm"]), (["comment", "reply", "dm"], ["reply", "dm"])],
)
def test_debug_only_prefetches_selected_sources(engagement, selected, expected):
    store, policy, version, day, calls = engagement
    store.debug_id = "debug:selected"
    store.put(
        "debug_run", {"day": day, "steps": [{"id": k, "state": "pending"} for k in selected]}, store.debug_id
    )
    workflow.interact(store, policy, day, version, kinds=("comment",))
    assert [kind for op, kind in calls if op == "inbox"] == [*expected, "comment"]


def test_three_inboxes_are_saved_before_an_outbound_comment_failure(engagement, monkeypatch):
    store, policy, version, day, calls = engagement
    policy['modules']['follow'] = policy['receive']['follow'] = policy['allowed']['follow'] = True
    policy['follow_terms'] = ['摄影']
    version = store.configure(policy, version)
    original = workflow.browser
    def browser(store, op, payload, action_id=None):
        if op == 'inbox' and payload['kind'] == 'follow':
            calls.append((op,'follow'))
            return {'items':[{'id':'fan','follows_me':True,'text':'摄影'}]}
        if op == 'interact' and payload['kind'] == 'comment':
            raise ExecutionPaused({'error':'输入框不可用'})
        return original(store, op, payload, action_id)
    monkeypatch.setattr(workflow, 'browser', browser)
    store.start_run(day,'comments','15:00',version)
    with pytest.raises(ExecutionPaused):
        workflow.interact(store,policy,day,version,kinds=('comment','reply'))
    assert calls[:4] == [('inbox','reply'),('inbox','dm'),('inbox','follow'),('inbox','comment')]
    assert {r['kind'] for r in messages.listing(store)['items']} == {'reply','dm','follow'}
