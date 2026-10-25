"""A successful PM preparation must still supply a runnable bridge binary."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _missing_package(monkeypatch):
    import pm
    import hermes_constants

    monkeypatch.setattr(hermes_constants, "find_node_executable", lambda executable: None)
    monkeypatch.setattr(hermes_constants, "with_hermes_node_path", dict)
    monkeypatch.setattr(pm, "ensure", lambda package, explicit: SimpleNamespace(env={}))
    monkeypatch.setattr(pm, "installed_package", lambda package: None)


@pytest.mark.parametrize("executable", ["npm", "node"])
def test_dashboard_reports_prepared_bridge_binary_missing(tmp_path, monkeypatch, executable):
    from hermes_cli.web_routers import messaging
    from gateway.platforms import whatsapp_common

    _missing_package(monkeypatch)
    bridge_dir = tmp_path / "bridge"
    bridge_dir.mkdir()
    (bridge_dir / "bridge.js").write_text("", encoding="utf-8")
    monkeypatch.setattr(whatsapp_common, "resolve_whatsapp_bridge_dir", lambda: bridge_dir)
    if executable == "npm":
        operation = lambda: messaging._ensure_whatsapp_bridge_dependencies(bridge_dir)
    else:
        monkeypatch.setattr(messaging, "_ensure_whatsapp_bridge_dependencies", lambda path: None)
        operation = lambda: messaging._spawn_whatsapp_pairing_process(tmp_path / "session", "bot")
    with pytest.raises(HTTPException) as caught:
        operation()
    if caught.value.status_code != 500 or executable not in caught.value.detail or "binary" not in caught.value.detail:
        pytest.fail(f"Unexpected dashboard error: {caught.value!r}")


