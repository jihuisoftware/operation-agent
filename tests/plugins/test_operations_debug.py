"""Development endpoints share the real Profile store and run only the selected workflow."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.testclient import TestClient

from devtools import operations_debug as debug
from plugins.operations.policy import DEFAULT
from plugins.operations.store import Store


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text("development:\n  operations_debug: true\n")
    store = Store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic="路线", goal="确认真实资料")
    policy["modules"].update(content=True, research=True, report=True)
    store.configure(policy, 0)
    return store


def test_single_task_has_persistent_detailed_logs_and_idempotent_requests(configured, monkeypatch):
    calls = []
    def produce(store, policy, day, version):
        calls.append("content")
        store.progress("正在生成", {"source_ids": ["source"]})
        store.put("content", {"day": day, "body": "完整正文", "ready": False}, "draft")
        return {"content_id": "draft", "ready": False, "missing": ["缺少图片"]}
    monkeypatch.setattr(debug.workflow, "produce", produce)
    monkeypatch.setattr(debug.workflow, "research", lambda *args: pytest.fail("不得执行其他任务"))
    body = {"task": "content", "version": 1, "request_id": "first"}
    result = debug.execute(body)
    assert result["state"] == "completed"
    assert not result['result']['ready']
    assert debug.execute(body) == result
    assert calls == ["content"]
    detail = debug.detail(result["id"])
    assert "完整正文" in str(detail["events"])
    assert any(e["data"].get("detail") == "正在生成" for e in detail["events"])
    debug.execute({**body, "request_id": "again"})
    assert calls == ["content", "content"]
    with configured.connection() as db:
        assert {r[0] for r in db.execute("SELECT stage FROM runs")} == {"content"}
    assert configured.policy()[0] == 1


@pytest.mark.parametrize("task", ("publish", "comment", "reply", "dm", "follow"))
def test_quick_external_task_requires_explicit_run_authorization(configured, monkeypatch, task):
    version, policy = configured.policy()
    policy["modules"][debug.TASKS[task][1]] = True
    policy["allowed"][task] = False
    configured.configure(policy, version)
    configured.claim("desktop", busy=True)
    calls = []

    def submit(*args, **kwargs):
        calls.append(task)
        return "已执行"

    monkeypatch.setattr(debug.workflow, "publish", submit)
    monkeypatch.setattr(debug.workflow, "interact", submit)
    body = {"task": task, "version": 2, "request_id": task, "mode": "quick"}
    with pytest.raises(HTTPException, match='真实外部动作'):
        debug.execute(body)
    assert not calls
    body['external_actions'] = 'execute_once'
    result = debug.execute(body)
    assert result['state'] == 'completed'
    assert calls == [task]
    assert debug.execute(body) == result
    assert debug.detail(result["id"])["actions"] == []
    assert configured.policy() == (2, policy)

    normal = {**body, "mode": "normal", "external_actions": None, "request_id": task + "-normal"}
    if task == 'publish':
        assert debug.execute(normal)['action_mode'] == 'publish_once'
        assert calls == [task, task]
    else:
        with pytest.raises(HTTPException, match='未授权'):
            debug.execute(normal)
        assert calls == [task]


@pytest.mark.parametrize("mode", ("normal", "quick"))
@pytest.mark.parametrize("exhausted", (False, True))
def test_debug_model_calls_ignore_quotas_without_spending_normal_allowance(configured, monkeypatch, mode, exhausted):
    from agent import auxiliary_client
    from plugins.operations import model
    from plugins.operations.policy import local_day
    version, policy = configured.policy()
    policy['model_calls'] = 1
    configured.configure(policy, version)
    day = local_day(policy)
    response = SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))])
    monkeypatch.setattr(auxiliary_client, 'call_llm', lambda **kwargs: response)
    if exhausted:
        model.generate(configured, policy, day, '常规调用', {})

    def produce(store, current, run_day, rule_version):
        for _ in range(3):
            model.generate(store, current, run_day, '调试调用', {})
        return '模型调用完成'

    monkeypatch.setattr(debug.workflow, 'produce', produce)
    body = {'task': 'content', 'version': 2, 'request_id': 'budget', 'mode': mode}
    def timeout(**kwargs):
        raise TimeoutError('模拟超时')
    monkeypatch.setattr(auxiliary_client, 'call_llm', timeout)
    assert debug.execute(body)['state'] == 'failed'
    monkeypatch.setattr(auxiliary_client, 'call_llm', lambda **kwargs: response)
    assert debug.execute({**body, 'request_id': 'retry'})['state'] == 'completed'
    with configured.connection() as db:
        calls = [json.loads(row[0]) for row in db.execute("SELECT data FROM events WHERE kind='model_call'")]
    assert len([call for call in calls if call.get('debug_id')]) == 4
    if not exhausted:
        model.generate(configured, policy, day, '常规调用', {})
    with pytest.raises(ValueError, match='模型调用额度'):
        model.generate(configured, policy, day, '超额常规调用', {})
    with configured.workspace.connection() as db:
        assert db.execute("SELECT sum(amount) FROM charges WHERE kind='model'").fetchone()[0] == 1
    assert configured.policy() == (2, policy)


def test_failures_are_durable_and_locks_and_permissions_still_apply(configured, monkeypatch):
    def fail(*args):
        raise ValueError("来源解析失败")
    monkeypatch.setattr(debug.workflow, "research", fail)
    body = {"task": "research", "version": 1, "request_id": "failure"}
    result = debug.execute(body)
    assert result["state"] == "failed"
    assert "ValueError: 来源解析失败" in str(debug.detail(result["id"])["events"])
    assert configured.lease("scheduled")
    with pytest.raises(HTTPException) as error:
        debug.execute({**body, "request_id": "busy"})
    assert error.value.status_code == 409
    configured.release("scheduled")
    version, policy = configured.policy()
    configured.configure({**policy, "paused": True}, version)
    with pytest.raises(HTTPException, match="全局暂停"):
        debug.execute({**body, "request_id": "paused", "version": 2})


def test_debug_http_is_disabled_by_default_and_cannot_cross_profiles(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    profile = tmp_path / "profiles" / "dev"
    profile.mkdir(parents=True)
    (tmp_path / "config.yaml").write_text("{}")
    (profile / "config.yaml").write_text("development:\n  operations_debug: true\n")
    from hermes_cli import web_server
    with TestClient(web_server.app) as client:
        path = "/api/plugins/operations/debug"
        assert client.get(path).status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        assert client.get(path).status_code == 404
        assert client.post(path + "/run", json={}).status_code == 404
        assert client.get(path + "?profile=dev").status_code == 200
        assert client.get(path + "/debug:other?profile=dev").status_code == 404


def test_comment_reply_is_independent_and_orphaned_runs_are_not_replayed(configured, monkeypatch):
    version, policy = configured.policy()
    policy["modules"]["comments"] = True
    configured.configure(policy, version)
    configured.claim("desktop", busy=True)
    calls = []
    def interact(*args, kinds):
        calls.append(kinds)
        return "已核对回复"
    monkeypatch.setattr(debug.workflow, "interact", interact)
    body = {"task": "reply", "request_id": "reply", "version": 2}
    result = debug.execute(body)
    assert calls == [("reply",)]
    result.update(state="running", ended=None)
    debug.update_record(configured, result)
    # The lease is gone, as after an interrupted owner. No new action is submitted.
    assert debug.detail(result["id"])["run"]["state"] == "interrupted"
    assert debug.execute(body)["state"] == "interrupted"
    assert calls == [("reply",)]


def test_running_http_request_exposes_live_progress_in_its_own_profile(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    from threading import Event
    from hermes_constants import get_hermes_home
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    dev = tmp_path / "profiles" / "dev"
    dev.mkdir(parents=True)
    for home in (tmp_path, dev):
        (home / "config.yaml").write_text("development:\n  operations_debug: true\n")
    started, finish = Event(), Event()
    def produce(store, *args):
        assert get_hermes_home() == dev
        store.progress("正在处理选定任务", {"source": "test"})
        started.set()
        assert finish.wait(15)
        return "已完成"
    monkeypatch.setattr(debug.workflow, "produce", produce)
    from hermes_cli import web_server
    with TestClient(web_server.app) as client:
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        base = "/api/plugins/operations"
        policy = deepcopy(DEFAULT)
        policy.update(enabled=True, topic="测试", goal="独立任务")
        policy["modules"]["content"] = True
        response = client.put(base + "/policy?profile=dev", json={"version": 0, "policy": policy})
        assert response.status_code == 200
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(client.post, base + "/debug/run?profile=dev",
                                  json={"version": 1, "task": "content", "request_id": "live"})
            try:
                assert started.wait(15)
                live = client.get(base + "/debug/debug:live?profile=dev")
                assert live.status_code == 200, live.text
                assert live.json()["run"]["state"] == "running"
                assert "正在处理选定任务" in live.text
                assert client.get(base + "/debug/debug:live").status_code == 404
            finally:
                finish.set()
            assert pending.result(timeout=15).json()["state"] == "completed"
