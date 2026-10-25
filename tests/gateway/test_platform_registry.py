"""Tests for the platform adapter registry and dynamic Platform enum."""

import threading
from unittest.mock import MagicMock

import pytest

from gateway.platform_registry import PlatformRegistry, PlatformEntry
from gateway.config import Platform, GatewayConfig
from hermes_cli import plugins_loader


# ── Platform enum dynamic members ─────────────────────────────────────────


class TestPlatformEnumDynamic:
    """Test that Platform enum accepts unknown values for plugin platforms."""




    def test_dynamic_member_with_hyphens(self):
        """Registered plugin platforms with hyphens work once registered."""
        from gateway.platform_registry import platform_registry as _reg

        entry = PlatformEntry(
            name="my-platform",
            label="My Platform",
            adapter_factory=lambda cfg: MagicMock(),
            check_fn=lambda: True,
            source="plugin",
        )
        _reg.register(entry)
        try:
            p = Platform("MY-PLATFORM")
            assert p is Platform("my-platform")
            assert p.value == "my-platform"
            assert p.name == "MY_PLATFORM"
        finally:
            _reg.unregister("my-platform")





# ── PlatformRegistry ──────────────────────────────────────────────────────


class TestPlatformRegistry:
    """Test the PlatformRegistry itself."""

    def _make_entry(self, name="test", check_ok=True, validate_ok=True, factory_ok=True):
        adapter_mock = MagicMock()
        return PlatformEntry(
            name=name,
            label=name.title(),
            adapter_factory=lambda cfg, _m=adapter_mock: _m if factory_ok else (_ for _ in ()).throw(RuntimeError("factory error")),
            check_fn=lambda: check_ok,
            validate_config=lambda cfg: validate_ok,
            required_env=[],
            source="plugin",
        ), adapter_mock

    def test_register_and_get(self):
        reg = PlatformRegistry()
        entry, _ = self._make_entry("alpha")
        reg.register(entry)
        assert reg.get("alpha") is entry
        assert reg.is_registered("alpha")


    def test_unregister(self):
        reg = PlatformRegistry()
        entry, _ = self._make_entry("beta")
        reg.register(entry)
        assert reg.unregister("beta") is True
        assert reg.get("beta") is None
        assert reg.unregister("beta") is False  # already gone


    def test_create_adapter_no_validate(self):
        """When validate_config is None, skip validation."""
        reg = PlatformRegistry()
        mock_adapter = MagicMock()
        entry = PlatformEntry(
            name="novalidate",
            label="NoValidate",
            adapter_factory=lambda cfg: mock_adapter,
            check_fn=lambda: True,
            validate_config=None,
            source="plugin",
        )
        reg.register(entry)
        assert reg.create_adapter("novalidate", MagicMock()) is mock_adapter

    def test_registered_names_includes_deferred_without_materializing(self):
        reg = PlatformRegistry()
        entry, _ = self._make_entry("concrete")
        loader = MagicMock()
        reg.register(entry)
        reg.register_deferred("deferred", loader)

        assert reg.registered_names() == {"concrete", "deferred"}
        loader.assert_not_called()
        assert reg.get("concrete") is entry
        assert reg.is_registered("deferred")


class TestEnsureDepsFn:
    """check_fn (PASSIVE probe) vs ensure_deps_fn (ACTIVE installer) split.

    Regression for #79812: Teams registered its passive probe as check_fn,
    so create_adapter() returned None before connect() could lazy-install —
    the SDK never installed.  The inverse wiring (active installer as
    check_fn) made status displays pip-install SDKs as a side effect.
    create_adapter() now runs ensure_deps_fn when check_fn is False.
    """

    def _entry(self, name, *, check_fn, ensure_deps_fn=None):
        adapter = MagicMock()
        entry = PlatformEntry(
            name=name,
            label=name.title(),
            adapter_factory=lambda cfg: adapter,
            check_fn=check_fn,
            ensure_deps_fn=ensure_deps_fn,
            source="plugin",
        )
        return entry, adapter

    def test_deps_present_skips_installer(self):
        """check_fn True → adapter created, ensure_deps_fn never called."""
        reg = PlatformRegistry()
        installer = MagicMock(return_value=True)
        entry, adapter = self._entry(
            "ready", check_fn=lambda: True, ensure_deps_fn=installer
        )
        reg.register(entry)
        assert reg.create_adapter("ready", MagicMock()) is adapter
        installer.assert_not_called()

    def test_missing_deps_runs_installer_then_creates(self):
        """check_fn False + ensure_deps_fn True → install runs, adapter created."""
        reg = PlatformRegistry()
        installer = MagicMock(return_value=True)
        entry, adapter = self._entry(
            "installable", check_fn=lambda: False, ensure_deps_fn=installer
        )
        reg.register(entry)
        assert reg.create_adapter("installable", MagicMock()) is adapter
        installer.assert_called_once()

    def test_install_failure_returns_none(self):
        """check_fn False + ensure_deps_fn False → no adapter."""
        reg = PlatformRegistry()
        installer = MagicMock(return_value=False)
        entry, _ = self._entry(
            "broken", check_fn=lambda: False, ensure_deps_fn=installer
        )
        reg.register(entry)
        assert reg.create_adapter("broken", MagicMock()) is None
        installer.assert_called_once()

    def test_no_installer_missing_deps_returns_none(self):
        """check_fn False + no ensure_deps_fn → hard block (legacy behavior)."""
        reg = PlatformRegistry()
        entry, _ = self._entry("blocked", check_fn=lambda: False)
        reg.register(entry)
        assert reg.create_adapter("blocked", MagicMock()) is None

    def test_installer_exception_returns_none(self):
        """ensure_deps_fn raising is caught, adapter not created."""
        reg = PlatformRegistry()

        def _boom():
            raise RuntimeError("pip exploded")

        entry, _ = self._entry(
            "explosive", check_fn=lambda: False, ensure_deps_fn=_boom
        )
        reg.register(entry)
        assert reg.create_adapter("explosive", MagicMock()) is None

    def test_check_fn_exception_falls_through_to_installer(self):
        """A raising check_fn is treated as deps-missing, installer still runs."""
        reg = PlatformRegistry()

        def _bad_probe():
            raise RuntimeError("probe error")

        installer = MagicMock(return_value=True)
        entry, adapter = self._entry(
            "flaky", check_fn=_bad_probe, ensure_deps_fn=installer
        )
        reg.register(entry)
        assert reg.create_adapter("flaky", MagicMock()) is adapter
        installer.assert_called_once()


# ── GatewayConfig integration ────────────────────────────────────────────


class TestGatewayConfigPluginPlatform:
    """Test that GatewayConfig parses and validates plugin platforms."""


    def test_get_connected_platforms_includes_registered_plugin(self):
        """Plugin platform with registry entry passes get_connected_platforms."""
        # Register a fake plugin platform
        from gateway.platform_registry import platform_registry as _reg

        test_entry = PlatformEntry(
            name="testplat",
            label="TestPlat",
            adapter_factory=lambda cfg: MagicMock(),
            check_fn=lambda: True,
            validate_config=lambda cfg: bool(cfg.extra.get("token")),
            source="plugin",
        )
        _reg.register(test_entry)
        try:
            data = {
                "platforms": {
                    "testplat": {"enabled": True, "extra": {"token": "abc"}},
                }
            }
            cfg = GatewayConfig.from_dict(data)
            connected = cfg.get_connected_platforms()
            connected_values = {p.value for p in connected}
            assert "testplat" in connected_values
        finally:
            _reg.unregister("testplat")


# ── Extended PlatformEntry fields ─────────────────────────────────────




# ── Cron platform resolution ─────────────────────────────────────────




# ── platforms.py integration ──────────────────────────────────────────


class TestPlatformsMerge:
    """Test get_all_platforms() merges with registry."""


    def test_get_all_platforms_includes_plugin(self):
        from hermes_cli.platforms import get_all_platforms
        from gateway.platform_registry import platform_registry as _reg

        _reg.register(PlatformEntry(
            name="testmerge",
            label="TestMerge",
            adapter_factory=lambda cfg: None,
            check_fn=lambda: True,
            source="plugin",
            emoji="🧪",
        ))
        try:
            merged = get_all_platforms()
            assert "testmerge" in merged
            assert "TestMerge" in merged["testmerge"].label
        finally:
            _reg.unregister("testmerge")


# ── apply_yaml_config_fn (PlatformEntry field + load_gateway_config dispatch) ──














@pytest.mark.parametrize("timeout, nested_sees_sibling", [(0.5, False), (0, True)])
def test_registry_walk_from_plugin_load_worker_does_not_wait_on_parent(monkeypatch, timeout, nested_sees_sibling):
    """register() re-walking the registry on its deadline worker must not block on its own or a sibling load;
    with the deadline disabled (inline loads) a nested get() must still load the sibling, as on main."""
    monkeypatch.setattr(plugins_loader, "_resolve_plugin_load_timeout", lambda: timeout)
    reg = PlatformRegistry()
    abandoned = []
    nested = []

    class Ctx:
        def _abandon_load(self):
            abandoned.append(True)

    discovery_lock = threading.RLock()  # like PluginManager._discovery_lock, held while joining the worker

    def make_loader(name):
        def register():
            reg.plugin_entries()
            if name == "reentrant":
                nested.append(reg.get("sibling") is not None)
            reg.register(PlatformEntry(name=name, label=name, adapter_factory=lambda cfg: None,
                                       check_fn=lambda: True, source="plugin"))

        def loader():
            with discovery_lock:
                plugins_loader.run_with_load_deadline(name, Ctx(), register)
        return loader

    for name in ("reentrant", "sibling"):
        reg.register_deferred(name, make_loader(name))

    assert sorted(e.name for e in reg.plugin_entries()) == ["reentrant", "sibling"]
    assert nested == [nested_sees_sibling]
    assert abandoned == []
