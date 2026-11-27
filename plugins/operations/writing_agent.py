"""A single isolated editorial turn on the active Profile's configured text model."""

from types import SimpleNamespace

from .model_errors import ModelServiceUnavailable


def complete(*, messages, max_tokens, timeout):
    from hermes_cli.config import load_config_readonly
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from agent.token_ledger import CONTEXT
    from run_agent import AIAgent

    model_config = load_config_readonly().get("model") or {}
    settings = model_config if isinstance(model_config, dict) else {"default": model_config}
    model = settings.get("default")
    if not model:
        raise ModelServiceUnavailable("请先配置用于写稿的文本模型")
    runtime = resolve_runtime_provider(
        requested=settings.get("provider"), target_model=model, explicit_base_url=settings.get("base_url")
    )
    agent = AIAgent(
        model=model,
        **{
            key: runtime.get(key)
            for key in (
                "provider",
                "api_key",
                "api_mode",
                "base_url",
                "credential_pool",
                "request_overrides",
                "command",
                "args",
            )
        },
        enabled_toolsets=[],
        skip_memory=True,
        skip_context_files=True,
        skip_background_review=True,
        max_tokens=max_tokens,
        max_iterations=1,
        run_budget_seconds=timeout,
        quiet_mode=True,
        ephemeral_system_prompt=messages[0]["content"],
    )
    # Manuscripts and bounded debug evidence belong to the operations store.
    agent._persist_disabled = True
    try:
        result = agent.run_conversation(messages[1]["content"], usage_context=CONTEXT.get())
        if (
            result.get("error")
            or result.get("failed")
            or result.get("interrupted")
            or result.get("completed") is False
        ):
            raise ModelServiceUnavailable(str(result.get("error") or "写稿 Agent 已中断"))
        total = agent.session_total_tokens
        last_message = next(
            (m for m in reversed(result.get("messages") or []) if m.get("role") == "assistant"), {}
        )
        choice = SimpleNamespace(
            message=SimpleNamespace(content=result.get("final_response")),
            finish_reason=result.get("finish_reason") or last_message.get("finish_reason"),
        )
        return SimpleNamespace(choices=[choice], usage={"total_tokens": total} if total else None)
    finally:
        agent.close()
