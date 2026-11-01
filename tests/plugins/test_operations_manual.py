"""Manual batches traverse real ledgers/queues without real network or account actions."""
from datetime import datetime, UTC

import pytest

from plugins.operations import workflow
from plugins.operations.manual import cron_request_id
from plugins.operations.runtime import ensure_schedule, tick
from plugins.operations.store import Store

NOW = datetime(2026, 10, 31, 9, 45, tzinfo=UTC)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    store = Store()
    _, policy = store.policy()
    policy.update(enabled=True, topic="个人成长", goal="记录可追溯的学习资料", account_id="me", knowledge=["九点开放"])
    policy["modules"] = {m: m != "follow" for m in policy["modules"]}
    policy["limits"]["publish"] = 3
    store.configure(policy, 0)
    return store


def test_manual_repeats_completed_stages_but_not_same_batch_and_refreshes_reports(store, monkeypatch):
    from plugins.operations.report import daily_report
    calls = []

    def stage(name):
        def execute(*args, **kwargs):
            calls.append(name)
            return "模拟完成"
        return execute

    for name in ("research", "organize", "analytics", "industry", "topics", "produce", "publish", "interact"):
        monkeypatch.setattr(workflow, name, stage(name))
    store.claim("mock-desktop", busy=True)
    previous = store.start_run("2026-10-31", "content", "09:40", 1)
    store.finish_run(previous, "completed", "原定时任务已完成")
    daily_report(store, "2026-10-31")
    for batch in ("click-one", "click-one", "click-two"):
        result = tick(store, NOW, request_id=batch)
        assert "完成" in result and "失败" not in result and "跳过" not in result
    assert calls == ["research", "organize", "analytics", "industry", "topics", "produce", "publish", "interact", "interact"] * 2
    assert len(store.objects("report")) == 3
    reports = {r["id"]: r["markdown"] for r in store.objects("report")}
    assert reports["report:2026-10-31:manual:click-two"].count("模拟完成") == len(calls)
    assert "模拟完成" not in reports["report:2026-10-31"]
    # A recovery of the same batch tomorrow still belongs to its original day.
    tick(Store(), datetime(2026, 11, 1, tzinfo=UTC), request_id="click-two")
    assert len(calls) == 18


def test_manual_uses_queue_targets_and_retains_shared_limits_and_unknown_fence(store):
    action = {"kind": "publish", "target": "same-content", "account_id": "me", "content": {}}
    ids = []
    for batch in ("one", "two", "three"):
        store.manual_run_id = batch
        identity = store.reserve_action(action, 1, "2026-10-31")
        ids.append(identity)
        assert store.reserve_action(action, 1, "2026-10-31") is None
        command = store.enqueue("publish", action, identity)
        claimed = store.claim("mock-desktop")
        assert claimed["payload"]["target"] == "same-content"
        store.acknowledge(command, "mock-desktop", {"state": "unknown" if batch == "three" else "published", "evidence": "模拟回执"})
    assert len(set(ids)) == 3
    restarted = Store()
    restarted.manual_run_id = "four"
    with pytest.raises(ValueError, match="未核对"):
        restarted.reserve_action(action, 1, "2026-10-31")
    from plugins.operations.service import resolve_action
    resolve_action(restarted, ids[-1], "confirmed_not_published", "模拟核对未发布")
    with pytest.raises(ValueError, match="每日动作额度"):
        restarted.reserve_action(action, 1, "2026-10-31")
    restarted.manual_run_id = None
    assert restarted.reserve_action(action, 1, "2026-11-01") is None


def test_manual_offline_no_source_and_failure_are_visible_and_pause_wins(store, monkeypatch):
    monkeypatch.setattr(workflow, "collect", lambda *args: None)
    summary = tick(store, NOW, request_id="offline")
    assert "信息采集：跳过" in summary and "运营日报：完成" in summary
    assert "桌面执行器离线" in summary and "没有可整理的来源" in summary
    def fail(*args):
        raise ValueError("模拟模型不可用")
    monkeypatch.setattr(workflow, "research", fail)
    with pytest.raises(RuntimeError, match="模拟模型不可用"):
        tick(store, NOW, request_id="failure")
    assert "模拟模型不可用" in store.objects("report")[0]["markdown"]
    version, policy = store.policy()
    store.configure({**policy, "paused": True}, version)
    before = len(store.snapshot()["runs"])
    assert "全局暂停" in tick(store, NOW, request_id="paused")
    assert len(store.snapshot()["runs"]) == before


@pytest.mark.platforms("macos")
def test_actual_cron_script_distinguishes_manual_from_scheduled_parent(store):
    from cron.executions import create_execution, mark_execution_running, finish_execution
    from cron.jobs import get_job
    from cron.scheduler_script import _run_job_script
    from cron.task_history import detail

    version, policy = store.policy()
    policy["modules"] = {m: m == "report" for m in policy["modules"]}
    policy["times"]["report"] = ["00:00"]
    store.configure(policy, version)
    job_id = ensure_schedule(store)
    job = get_job(job_id)
    plan = detail(job)
    assert plan['plan']['definition']['topic'] == '个人成长'
    assert plan['execution'] is None
    for instant in (None, "2026-10-31T00:00:00+00:00"):
        execution = create_execution(job_id, source="manual-contract-test", scheduled_instant=instant)
        assert mark_execution_running(execution["id"])
        assert cron_request_id(store) is None  # The owner itself is not the script child.
        try:
            success, output = _run_job_script(job["script"])
            assert success, output
            assert ("手动运营" in output) == (instant is None)
            if instant is None:
                assert any(r["slot"] == "manual:" + execution["id"] for r in Store().snapshot()["runs"])
                current = detail(job)
                assert current['execution']['status'] == 'running'
                report_step = next(s for s in current['steps'] if s['id'].startswith('report:'))
                assert report_step['state'] == 'completed'
                report_event = next(e for e in current['events'] if e['data'].get('kind') == 'report')
                assert report_event['data']['result']['markdown']
        finally:
            finish_execution(execution["id"], success=True)
    execution_id = detail(job)['attempts'][-1]['id']
    historical = detail(job, execution_id)
    assert historical['execution']['id'] == execution_id
    assert historical['context']['manual'] is True


def test_saved_incomplete_draft_is_not_reported_as_ready_or_published(store, monkeypatch):
    version, policy = store.policy()
    policy['modules'] = {m: m in {'content', 'report'} for m in policy['modules']}
    policy['allowed'] = {a: False for a in policy['allowed']}
    policy.update(account_id='', knowledge=[])
    store.configure(policy, version)
    monkeypatch.setattr(workflow, 'produce', lambda *args: {
        'content_id': 'draft', 'ready': False, 'missing': ['缺少获授权图片'], 'reason': '自动检查通过'})
    result = tick(store, NOW, request_id='incomplete')
    assert '待完善 1' in result
    assert '草稿已保存' in result and '尚不可发布' in result
    assert '已核对成功 0 条' in result
    assert '图文发布：未加入当前生效计划' in result
    assert '填写小红书账号 ID' not in result and '补充已确认的回复知识' in result
    assert any(r['state'] == 'needs_attention' for r in store.snapshot()['runs'])
    assert 'needs_attention' in store.objects('report')[0]['markdown']
