"""A fresh native input from an adapter that declares ``authorization_is_upstream`` is
admitted without a principal allowlist (#139199).

The unified gateway's durable admission re-checks authorization inside
``session_envelope._validate_native`` with ``allow_adapter_delegation`` derived from the
relay seal / role reauthorization only. A direct adapter whose entire authorization model
IS the upstream (A2A peers: bearer-token authenticated in ``do_POST``) has no relay seal
and no roles, so the re-check fell to the principal allowlist and — with no
``A2A_ALLOWED_USERS`` — default-denied every fresh native message that the same gateway's
inbound filter had just accepted.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.config import GatewayConfig, Platform
from gateway.platforms.event import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session_envelope import snapshot_native
from hermes_state_runtime import RuntimeStoreError


def _clear_authz_env(monkeypatch) -> None:
    for key in (
        "A2A_ALLOWED_USERS",
        "A2A_ALLOW_ALL_USERS",
        "DISCORD_ALLOWED_USERS",
        "GATEWAY_ALLOWED_USERS",
        "GATEWAY_ALLOW_ALL_USERS",
    ):
        monkeypatch.delenv(key, raising=False)


def _fresh_native_event(
    source, text="hello from a peer", message_id="m1"
) -> MessageEvent:
    return MessageEvent(
        text=text, message_type=MessageType.TEXT, message_id=message_id, source=source
    )




@pytest.mark.asyncio
async def test_non_upstream_adapter_still_default_denies_without_allowlist(
    tmp_path, monkeypatch
):
    from gateway.session import SessionSource

    _clear_authz_env(monkeypatch)
    runner = GatewayRunner(GatewayConfig(sessions_dir=tmp_path / "sessions"))
    runner.adapters = {
        Platform.DISCORD: SimpleNamespace(
            send=AsyncMock(),
            authorization_is_upstream=False,
            enforces_own_access_policy=False,
        )
    }
    discord_source = SessionSource(
        platform=Platform.DISCORD,
        user_id="123",
        chat_id="456",
        user_name="someone",
        chat_type="dm",
    )
    with pytest.raises(RuntimeStoreError, match="permission_denied"):
        snapshot_native(runner, _fresh_native_event(discord_source))
