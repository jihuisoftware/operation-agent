"""Operations discovery filters every catalog source without delisting installed plugins."""

import json

import pytest

import hermes_yaml as yaml
from hermes_cli import plugin_catalog as catalog
from hermes_cli import plugins_cmd_catalog as commands


def _entry(name, category, **extra):
    return {"name": name, "repo": f"https://github.com/example/{name}", "sha": "a" * 40,
            "description": "Test integration.", "maintainer": "example", "category": category,
            "tier": "official", "onboarding": True, **extra}


@pytest.mark.parametrize("live", [False, True])
def test_discovery_scope_survives_live_refresh_and_offline_fallback(tmp_path, monkeypatch, capsys, live):
    from hermes_cli.plugin_catalog_presence import onboarding_names
    from tools.connectors.catalog_tool import _plugin_rows

    entries = [_entry("writer", "models"), _entry("developer", "tools"),
               _entry("chat-adapter", "platform"), _entry("pc-only", "models", platforms=["windows"])]
    root = tmp_path / "catalog"
    root.mkdir()
    for entry in entries:
        (root / f"{entry['name']}.yaml").write_text(yaml.safe_dump(entry))
    monkeypatch.setattr(catalog, "get_catalog_dir", lambda: root)
    monkeypatch.setattr(catalog, "fetch_live_catalog", lambda: {"entries": entries} if live else None)
    monkeypatch.setattr(catalog, "in_tree_catalog_time", lambda: None)
    monkeypatch.setattr(commands, "resolved_removed_entries", list)
    monkeypatch.setattr("hermes_cli.plugins_cmd._read_install_metadata", dict)

    commands.cmd_search(json_output=True)
    assert [e["name"] for e in json.loads(capsys.readouterr().out)["results"]] == ["writer"]
    assert [e["name"] for e in commands.installed_catalog_state({})["entries"]] == ["writer"]
    assert onboarding_names() == ["writer"]
    assert [e["id"] for e in _plugin_rows("")] == ["writer"]

    # Explicit install/update/migration resolution is not a browse operation.
    assert catalog.get_live_catalog_entry("developer").repo == "https://github.com/example/developer"
    monkeypatch.setattr(commands, "catalog_install_record", lambda path: None)
    installed = {"developer": {"dir": str(tmp_path / "installed"), "runtime_status": "disabled"}}
    rows = {e["name"]: e for e in commands.installed_catalog_state(installed)["entries"]}
    assert rows["developer"]["installed"] is True
    assert rows["developer"]["runtime_status"] == "disabled"


def test_curated_operations_entry_still_respects_platform_and_retirement():
    from hermes_cli.plugin_catalog_scope import browse_catalog

    entries = [_entry("rss-reader", "desktop"), _entry("spotify", "web"),
               _entry("rss-reader", "desktop", platforms=["linux"])]
    parsed = [catalog.entry_from_mapping(entry, entry["name"]) for entry in entries]
    assert browse_catalog(parsed) == [parsed[0]]
