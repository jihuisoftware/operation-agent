"""The operations build narrows existing profiles without rewriting their state."""

import pytest


@pytest.mark.parametrize("loader", ["merged", "runtime"])
def test_legacy_profile_keeps_credentials_and_history_but_not_retired_services(tmp_path, monkeypatch, loader):
    from hermes_cli.config import load_config, read_raw_config
    from gateway.run import _load_gateway_config

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    original = """display:
  language: en
model:
  provider: custom
  default: content-model
  api_key: unchanged-secret
agent:
  disabled_toolsets: [tts]
  coding_context: focus
platform_toolsets:
  cli: [hermes-cli, discord, delegation, kanban]
plugins:
  enabled: [google_meet]
  disabled: [my-disabled-plugin]
kanban:
  dispatch_in_gateway: true
  notify_in_gateway: true
curator:
  enabled: true
gateway:
  loop_watchdog: false
  platforms:
    webhook:
      enabled: true
      extra:
        port: 18080
platform_hints:
  desktop:
    append: Keep the brand voice.
"""
    path = tmp_path / "config.yaml"
    path.write_text(original)
    history = tmp_path / "sessions"
    history.mkdir()
    (history / "keep.json").write_text('{"content":"saved content"}')

    config = load_config() if loader == "merged" else _load_gateway_config(path)

    assert config["display"]["language"] == "zh"
    assert config["model"]["default"] == "content-model"
    assert config["model"]["api_key"] == "unchanged-secret"
    assert "tts" in config["agent"]["disabled_toolsets"]
    assert {"delegation", "discord"} <= set(config["agent"]["disabled_toolsets"])
    assert {"google_meet", "my-disabled-plugin"} <= set(config["plugins"]["disabled"])
    assert config["agent"]["coding_context"] == "off"
    assert config["kanban"]["dispatch_in_gateway"] is True
    assert config["kanban"]["notify_in_gateway"] is False
    assert config["curator"]["enabled"] is False
    assert config["gateway"]["loop_watchdog"] is False
    assert config["gateway"]["platforms"]["webhook"]["enabled"] is False
    assert config["gateway"]["platforms"]["webhook"]["extra"]["port"] == 18080
    assert "Keep the brand voice." in config["platform_hints"]["desktop"]["append"]
    assert "小红书" in config["platform_hints"]["desktop"]["append"]
    assert read_raw_config()["kanban"]["dispatch_in_gateway"] is True
    assert path.read_text() == original
    assert (history / "keep.json").read_text() == '{"content":"saved content"}'


def test_desktop_selection_keeps_content_tools_and_respects_user_opt_out(tmp_path, monkeypatch):
    from hermes_cli.config import load_config
    from hermes_cli.tools_config import _get_effective_configurable_toolsets, _get_platform_tools
    from gateway.rpc.server import _load_disabled_toolsets, _load_enabled_toolsets

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_TUI_TOOLSETS", raising=False)
    (tmp_path / "config.yaml").write_text("agent:\n  disabled_toolsets: [tts]\n")

    selected = set(_load_enabled_toolsets("desktop"))
    assert {"web", "browser", "file", "vision", "skills", "cronjob", "desktop_ui"} <= selected
    assert not selected.intersection({"tts", "delegation", "kanban", "catalog", "discord", "connections"})
    assert "delegation" in _load_disabled_toolsets()
    catalog = {row[0] for row in _get_effective_configurable_toolsets()}
    assert {"web", "image_gen", "cronjob"} <= catalog
    assert "kanban" in catalog
    assert not catalog.intersection({"delegation", "discord", "connections"})

    # An explicit empty selection is still a zero-tool session.
    (tmp_path / "config.yaml").write_text("platform_toolsets:\n  cli: []\n")
    assert _get_platform_tools(load_config(), "cli") == set()
    assert _load_enabled_toolsets("desktop") == []


def test_public_platform_env_cannot_start_ingress_but_local_runtime_settings_survive(tmp_path, monkeypatch):
    from gateway.config import Platform, load_gateway_config

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("API_SERVER_ENABLED", "true")
    monkeypatch.setenv("WEBHOOK_ENABLED", "true")
    (tmp_path / "config.yaml").write_text("gateway:\n  multiplex_profiles: true\n")
    config = load_gateway_config()
    assert config.multiplex_profiles is True
    assert Platform.API_SERVER not in config.get_connected_platforms()
    assert Platform.WEBHOOK not in config.get_connected_platforms()


def test_existing_mcp_server_is_not_started_or_advertised(tmp_path, monkeypatch):
    from hermes_cli.config import load_config
    from hermes_cli.tools_config import _get_platform_tools, enabled_mcp_server_names
    from tools.mcp_tool_config import _load_mcp_config

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    original = "mcp_servers:\n  old-integration:\n    command: unused-server\n    enabled: true\n"
    path = tmp_path / "config.yaml"
    path.write_text(original)

    assert _load_mcp_config() == {}
    assert enabled_mcp_server_names(load_config()) == set()
    assert "old-integration" not in _get_platform_tools(load_config(), "cli")
    assert path.read_text() == original
