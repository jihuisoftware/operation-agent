"""Retired bot configuration must never reconnect while Desktop starts its runtime."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from gateway.config import Platform, PlatformConfig, load_gateway_config
from gateway.run_adapters import GatewayAdapterLifecycleMixin


def test_saved_bot_credentials_are_ignored_but_runtime_settings_survive(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "old-telegram-token")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "old-discord-token")
    monkeypatch.setenv("GATEWAY_RELAY_URL", "wss://retired.example/relay")
    config_file = tmp_path / "config.yaml"
    original = """gateway:
  multiplex_profiles: true
  loop_watchdog: false
  platforms:
    telegram:
      enabled: true
      token: old-telegram-token
    relay:
      enabled: true
platforms:
  discord:
    enabled: true
    token: old-discord-token
  webhook:
    enabled: true
    extra:
      port: 18080
"""
    config_file.write_text(original)
    (tmp_path / "gateway.json").write_text('{"platforms":{"slack":{"enabled":true,"token":"old"}}}')

    config = load_gateway_config()

    assert set(config.platforms) == {Platform.WEBHOOK}
    assert config.platforms[Platform.WEBHOOK].extra["port"] == 18080
    assert config.multiplex_profiles is True
    assert config.loop_watchdog is False
    assert config_file.read_text() == original


@pytest.mark.parametrize("platform", [Platform.TELEGRAM, Platform.DISCORD, Platform.RELAY, Platform.MSGRAPH_WEBHOOK])
def test_adapter_factory_never_enters_retired_transports(platform):
    runner = SimpleNamespace(_instantiate_adapter=Mock(side_effect=AssertionError("external transport loaded")))
    assert GatewayAdapterLifecycleMixin._create_adapter(runner, platform, PlatformConfig(enabled=True)) is None
    runner._instantiate_adapter.assert_not_called()


def test_generic_webhook_adapter_keeps_runtime_ownership():
    adapter = SimpleNamespace()
    runner = SimpleNamespace(_instantiate_adapter=Mock(return_value=adapter))
    assert GatewayAdapterLifecycleMixin._create_adapter(runner, Platform.WEBHOOK, PlatformConfig(enabled=True)) is adapter
    assert adapter.gateway_runner is runner
