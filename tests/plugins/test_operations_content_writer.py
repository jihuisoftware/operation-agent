"""Writing checkpoints, bounded editorial work and independent debug variants."""

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from devtools import operations_debug as debug
from plugins.operations import content, content_writer as writer
from plugins.operations.model_errors import ModelOutputError
from tests.plugins.operations_support import editorial_outline
from tests.plugins.test_operations_content_autorepair import configured


def response(value):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(value)))],
        usage={"total_tokens": 25},
    )


def draft(body="逐项核对来源中的限制。"):
    return {"title": "工程实践如何核对", "body": body, "source_ids": ["source"], "asset_ids": []}


def setup(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, monkeypatch)
    from plugins.operations import automatic_review

    monkeypatch.setattr(
        automatic_review,
        "finish_production",
        lambda store, policy, day, version, row, sources: {"content_id": row["id"], "ready": False},
    )
    return store, policy, day


def test_resume_outline_after_provider_error_and_shorten_only_once(tmp_path, monkeypatch):
    store, policy, day = setup(tmp_path, monkeypatch)
    calls = []

    def provider(**kwargs):
        payload = json.loads(kwargs["messages"][1]["content"])
        calls.append(payload)
        if len(calls) == 1:
            return response(editorial_outline(payload))
        if len(calls) == 2:
            raise TimeoutError("测试超时")
        if len(calls) == 3:
            return response(draft("过" * 901))
        assert "901" in payload["editor_feedback"] and payload["sources"][0]["text"]
        return response(draft())

    monkeypatch.setattr(writer, "complete", provider)
    from plugins.operations.model_errors import ModelServiceUnavailable

    with pytest.raises(ModelServiceUnavailable, match="撰写正文"):
        content.produce_content(store, policy, day, 1)
    assert len(store.objects("writing_outline")) == 1 and not store.objects("content")
    result = content.produce_content(store, policy, day, 1)
    assert result["writing_state"] == "resumed_outline"
    assert content.produce_content(store, policy, day, 1)["writing_state"] == "reused"
    assert len(calls) == 4
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM model_budget_usage").fetchone()[0] == 4


def test_debug_new_variant_preserves_original_and_replaying_request_is_free(tmp_path, monkeypatch):
    store, policy, day = setup(tmp_path, monkeypatch)
    (tmp_path / "config.yaml").write_text("development:\n  operations_debug: true\n")
    plans = []

    def provider(**kwargs):
        data = json.loads(kwargs["messages"][1]["content"])
        if "outline" not in data:
            plans.append(data)
            return response(editorial_outline(data))
        return response(draft(f"正文角度{len(plans)}"))

    monkeypatch.setattr(writer, "complete", provider)
    original = content.produce_content(store, policy, day, 1)
    body = {"task": "content", "version": 1, "request_id": "another", "draft_mode": "new_variant"}
    new = debug.execute(body, store.path)
    assert new["draft_mode"] == "new_variant" and new["result"]["content_id"] != original["content_id"]
    assert plans[1]["prior_article"]["body"] == "正文角度1"
    assert debug.execute(body, store.path)["result"] == new["result"]
    assert content.produce_content(store, policy, day, 1)["content_id"] == original["content_id"]
    assert len(plans) == len(store.objects("content")) == 2
    with pytest.raises(HTTPException) as conflict:
        debug.execute({**body, "draft_mode": "reuse"}, store.path)
    assert conflict.value.status_code == 409


@pytest.mark.parametrize("unexpected", [{"source_ids": ["another"]}, {"asset_ids": ["other"]}])
def test_writer_rejects_unprovided_ids(unexpected):
    with pytest.raises(ModelOutputError):
        writer.checked_draft({**draft(), **unexpected}, {"source"}, set())


def test_changed_source_prevents_saving_stale_manuscript(tmp_path, monkeypatch):
    store, policy, day = setup(tmp_path, monkeypatch)

    def provider(**kwargs):
        data = json.loads(kwargs["messages"][1]["content"])
        if "outline" not in data:
            return response(editorial_outline(data))
        with store.connection() as db:
            db.execute("UPDATE objects SET data=json_set(data,'$.text','更正后的原文') WHERE id='source'")
        return response(draft())

    from plugins.operations.outcomes import StageSkipped
    monkeypatch.setattr(writer, "complete", provider)
    with pytest.raises(StageSkipped):
        content.produce_content(store, policy, day, 1)
    assert not store.objects("content")


def test_agent_adapter_forwards_profile_transport_and_uses_owned_task(monkeypatch):
    from unittest.mock import Mock
    from agent.token_ledger import bind
    from plugins.operations.writing_agent import complete

    monkeypatch.setattr("hermes_cli.config.load_config_readonly", lambda: {"model": {"default": "editor", "provider": "local"}})
    resolve = Mock(return_value={"provider": "local", "base_url": "http://localhost"})
    monkeypatch.setattr("hermes_cli.runtime_provider.resolve_runtime_provider", resolve)
    agent = Mock(session_total_tokens=25)
    agent.run_conversation.return_value = {"completed": True, "final_response": '{"title":"稿件"}',
                                           "messages": [{"role": "assistant", "finish_reason": "stop"}]}
    constructor = Mock(return_value=agent)
    monkeypatch.setattr("run_agent.AIAgent", constructor)
    messages = [{"role": "system", "content": "编辑说明"}, {"role": "user", "content": "公开证据"}]
    with bind({"task_id": "writing"}):
        result = complete(messages=messages, timeout=12, max_tokens=80)
    resolve.assert_called_once_with(requested="local", target_model="editor", explicit_base_url=None)
    options = constructor.call_args.kwargs
    assert options["model"] == "editor" and options["enabled_toolsets"] == []
    assert options["skip_memory"] and options["ephemeral_system_prompt"] == "编辑说明"
    agent.run_conversation.assert_called_once_with("公开证据", usage_context={"task_id": "writing"})
    agent.close.assert_called_once_with()
    assert result.choices[0].finish_reason == "stop" and result.usage["total_tokens"] == 25
