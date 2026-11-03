"""The debug batch uses real workflow/storage/queue code with simulated provider receipts."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from devtools import operations_debug as debug
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text("development:\n  operations_debug: true\n")
    store = Store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic="步行", goal="路线资料", account_id="me",
                  sources=["https://example.org/walk"], knowledge=["开放时间为九点。"], follow_terms=["步行"])
    policy["modules"] = {k: True for k in policy["modules"]}
    policy["allowed"] = {k: True for k in policy["allowed"]}
    store.configure(policy, 0)
    store.put("asset", {"authorized": True, "name": "自有图片.png"}, "image")
    from tools import web_tools
    monkeypatch.setattr(web_tools, "web_search_tool", lambda *a, **k: json.dumps({"data": {"web": []}}))
    async def extract(*args, **kwargs):
        return json.dumps({"results": [{"content": "步行路线开放时间为九点。"}]})
    monkeypatch.setattr(web_tools, "web_extract_tool", extract)
    from agent import auxiliary_client
    monkeypatch.setattr(auxiliary_client, "call_llm", model)
    original = Store.command
    submitted = []
    def consume(self, identity):
        command = self.claim("simulated-desktop")
        while command and command['kind'] == 'verify' and command['id'] != identity:
            self.acknowledge(command['id'], 'simulated-desktop', {'state': 'unknown', 'evidence': '只读核对：平台仍在审核'})
            command = self.claim('simulated-desktop')
        assert command["id"] == identity
        payload = command["payload"]
        if command["kind"] == "inbox":
            result = {"items": [{"id": payload["kind"] + ":1", "text": "步行，开放时间？", "inbound": True, "follows_me": True}]}
        else:
            submitted.append(payload)
            result = {"state": "confirmed", "evidence": "模拟页面回执", "url": "https://example.org/result"}
        self.acknowledge(identity, "simulated-desktop", result)
        return original(self, identity)
    monkeypatch.setattr(debug.DebugStore, "command", consume)
    store.claim("simulated-desktop", busy=True)
    return store, submitted


def model(**kwargs):
    data = json.loads(kwargs["messages"][1]["content"])
    if data.get('task') == 'industry_analysis':
        from tests.plugins.operations_support import industry_response as finding
        result = finding(data)
    elif data.get("task") == "organize_sources":
        from tests.plugins.operations_support import organized_response
        result = organized_response(data)
    elif "candidates" in data:
        result = {"actions": [{"id": data["candidates"][0]["id"], "text": "开放时间为九点。", "knowledge_ids": [0]}]}
    elif "content" in data:
        result = {"pass": True, "reason": "来源一致"}
    elif "assets" in data:
        assert data["selected_topic"]["title"] == "步行路线"
        result = {"title": "步行路线", "body": "开放时间为九点。", "asset_ids": ["image"], "source_ids": [data["sources"][0]["id"]]}
    else:
        result = {"topics": [{"title": "步行路线", "reason": "有来源", "source_ids": [data["sources"][0]["id"]]}]}
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(result)))], usage=None)


def test_complete_pipeline_persists_lineage_receipts_and_report_without_replay(environment, monkeypatch):
    store, submitted = environment
    original = debug.workflow.produce
    def produce(*args):
        result = original(*args)
        content = store.objects("content")[0]
        # A later editable version must not replace this batch's chosen output.
        store.put("content", {**content, "title": "其他版本"}, "other")
        return result
    monkeypatch.setattr(debug.workflow, "produce", produce)
    body = {"task": "pipeline", "version": 1, "request_id": "full"}
    result = debug.execute(body)
    assert result["state"] == "completed", result["detail"]
    assert [p["kind"] for p in submitted] == ["publish", "comment", "reply", "dm", "follow"]
    assert submitted[0]["content"]["id"] == result["content_id"]
    assert submitted[0]["content"]["selected_topic"]["title"] == "步行路线"
    assert debug.execute(body) == result
    assert len(submitted) == 5
    detail = debug.detail(result["id"])
    assert {e["data"]["step_id"] for e in detail["events"] if e["kind"] == "pipeline_step_end"} == set(debug.TASKS)
    assert all(s["started"] and s["ended"] and s["duration_ms"] >= 0 for s in result["steps"])
    assert len({s["run_id"] for s in result["steps"]}) == len(debug.TASKS)
    assert all(a["result"]["evidence"] == "模拟页面回执" for a in detail["actions"])
    assert "已核对成功 5 次" in store.objects("report")[0]["markdown"]
    assert store.policy()[0] == 1


def test_unverified_receipt_is_not_a_pipeline_pass_and_is_kept_in_report(environment, monkeypatch):
    store, _ = environment
    original = Store.acknowledge
    def acknowledge(self, identity, worker, result):
        if "state" in result:
            result = {**result, "state": "submitted", "evidence": "模拟页面待审核"}
        return original(self, identity, worker, result)
    monkeypatch.setattr(Store, "acknowledge", acknowledge)
    result = debug.execute({"task": "pipeline", "version": 1, "request_id": "unknown"})
    assert result["state"] == "needs_attention"
    assert result["external_actions"] == {"total": 5, "confirmed": 0}
    assert "已核对成功 0 次" in store.objects("report")[0]["markdown"]
    assert all(a["state"] == "submitted" for a in debug.detail(result["id"])["actions"])


def test_failed_topics_blocks_old_content_publish_but_independent_steps_and_report_continue(environment, monkeypatch):
    store, submitted = environment
    day = local_day(store.policy()[1])
    store.put("content", {"day": day, "title": "旧草稿", "body": "不能冒充本轮结果", "ready": True}, "old")
    from agent import auxiliary_client
    def fail_topics(**kwargs):
        data = json.loads(kwargs["messages"][1]["content"])
        if "candidates" not in data and data.get('task') not in ('organize_sources', 'industry_analysis'):
            raise ValueError("选题模型不可用")
        return model(**kwargs)
    monkeypatch.setattr(auxiliary_client, "call_llm", fail_topics)
    result = debug.execute({"task": "pipeline", "version": 1, "request_id": "failed"})
    assert result["state"] == "failed"
    steps = {s["id"]: s for s in result["steps"]}
    assert steps["topics"]["state"] == "failed"
    assert steps["content"]["state"] == steps["publish"]["state"] == "skipped"
    assert steps["report"]["state"] == "completed"
    assert {p["kind"] for p in submitted} == {"comment", "reply", "dm", "follow"}
    assert "ValueError: 选题模型不可用" in str(debug.detail(result["id"])["events"])
    assert "选题模型不可用" in store.objects("report")[0]["markdown"]


def test_pause_during_batch_stops_following_actions_and_still_saves_diagnostic_report(environment, monkeypatch):
    store, submitted = environment
    original = debug.workflow.research
    def pause(*args):
        result = original(*args)
        version, policy = store.policy()
        store.configure({**policy, "paused": True}, version)
        return result
    monkeypatch.setattr(debug.workflow, "research", pause)
    result = debug.execute({"task": "pipeline", "version": 1, "request_id": "paused"})
    assert result["state"] == "needs_attention"
    assert not submitted
    assert all(s["state"] == "skipped" for s in result["steps"][1:-1])
    assert result["steps"][-1]["state"] == "completed"
    assert store.policy()[1]["paused"]


def test_disabled_modules_are_not_enabled_and_interrupted_batch_cannot_replay(environment):
    store, submitted = environment
    version, policy = store.policy()
    policy["modules"] = {k: False for k in policy["modules"]}
    policy["enabled"] = False
    store.configure(policy, version)
    body = {"task": "pipeline", "version": 2, "request_id": "disabled"}
    result = debug.execute(body)
    assert result["state"] == "needs_attention"
    assert not submitted
    assert all(s["state"] == "skipped" for s in result["steps"][:-1])
    assert len(store.objects("report")) == 1
    result.update(state="running")
    result["steps"][0]["state"] = "running"
    debug.update_record(store, result)
    assert debug.execute(body)["state"] == "interrupted"
    assert debug.detail(result["id"])["run"]["steps"][0]["state"] == "interrupted"
    assert store.policy()[1] == policy


def test_quick_pipeline_covers_internal_modules_without_submitting_external_actions(environment):
    store, submitted = environment
    version, policy = store.policy()
    policy["modules"] = {key: key == "report" for key in policy["modules"]}
    store.configure(policy, version)

    result = debug.execute({"task": "pipeline", "version": 2, "request_id": "quick-coverage", "mode": "quick"})

    internal = {key for key, (_, module) in debug.TASKS.items() if module not in {"publish", "comments", "dm", "follow", "report"}}
    steps = {step["id"]: step for step in result["steps"]}
    assert all("模块未启用" not in steps[key]["detail"] for key in internal)
    assert all(steps[key]["state"] == "completed" for key in internal)
    assert all("快速测试仅检查外部动作" in steps[key]["detail"] for key in {"publish", "comment", "reply", "dm", "follow"})
    assert steps["report"]["state"] == "completed"
    assert not submitted
    assert store.run_options is None
    assert store.policy()[1]["modules"] == policy["modules"]


def test_partial_collection_preserves_usable_evidence_for_following_steps(environment, monkeypatch):
    from tools import web_tools
    store, _ = environment
    monkeypatch.setattr(web_tools, 'web_search_tool', lambda *a, **k: '{"error":"搜索服务不可用"}')
    result = debug.execute({'task': 'pipeline', 'version': 1, 'request_id': 'partial-research'})
    steps = {step['id']: step for step in result['steps']}
    assert steps['research']['state'] == 'needs_attention'
    assert steps['research']['result']['usable'] == 1
    assert steps['organize']['state'] == steps['topics']['state'] == 'completed'
    assert result['state'] == 'needs_attention'
    assert '搜索服务不可用' in store.objects('report')[0]['markdown']
