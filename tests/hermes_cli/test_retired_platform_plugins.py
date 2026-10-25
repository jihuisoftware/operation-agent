"""An old opt-in cannot reactivate messaging when Desktop discovers plugins."""


def test_discovery_skips_platform_plugin_but_loads_regular_plugin(tmp_path, monkeypatch):
    from hermes_cli import plugins

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    monkeypatch.setattr(plugins, "get_bundled_plugins_dir", lambda: bundled)
    monkeypatch.setattr(plugins.PluginManager, "_scan_entry_points", lambda self: [])
    (tmp_path / "config.yaml").write_text("plugins:\n  enabled: [retired-bot, ordinary-tool]\n")
    for name, kind in (("retired-bot", "platform"), ("ordinary-tool", "standalone")):
        folder = tmp_path / "plugins" / name
        folder.mkdir(parents=True)
        (folder / "plugin.yaml").write_text(f"name: {name}\nversion: 1.0.0\nkind: {kind}\n")
        (folder / "__init__.py").write_text(
            "from pathlib import Path\n"
            "def register(ctx):\n"
            "    Path(__file__).with_name('loaded').write_text('yes')\n"
        )

    manager = plugins.PluginManager()
    try:
        manager.discover_and_load()
        assert not (tmp_path / "plugins/retired-bot/loaded").exists()
        assert (tmp_path / "plugins/ordinary-tool/loaded").exists()
    finally:
        manager.unload()
