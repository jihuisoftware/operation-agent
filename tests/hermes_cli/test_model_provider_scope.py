"""Provider discovery follows the product scope without destroying stored credentials."""

def test_catalog_and_account_lists_share_scope_and_labels():
    from hermes_cli.model_provider_scope import HIDDEN_MODEL_PROVIDERS, provider_label
    from hermes_cli.models_catalog_static import listed_canonical_providers
    from hermes_cli.provider_catalog import provider_catalog
    from hermes_cli.web_routers.oauth import _build_oauth_catalog

    catalog = {p.slug: p for p in provider_catalog()}
    assert "nous" not in catalog
    assert not HIDDEN_MODEL_PROVIDERS.intersection(catalog)
    assert set(catalog) == {p.slug for p in listed_canonical_providers()}
    for row in _build_oauth_catalog():
        assert row["id"] not in HIDDEN_MODEL_PROVIDERS
        assert row["name"] == provider_label(row["id"], row["name"])
    assert catalog["deepseek"].label == "深度求索"
    assert catalog["alibaba"].label != catalog["alibaba-cn"].label


def test_saved_hidden_provider_stays_off_picker_without_losing_credentials(tmp_path, monkeypatch):
    from hermes_cli import inventory, model_switch
    from hermes_cli.web_routers import config_env
    from hermes_cli.config import load_config

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    config = tmp_path / "config.yaml"
    config.write_text("model:\n  provider: nous\n  default: existing-model\nnous:\n  guest: true\n")
    env = tmp_path / ".env"
    env.write_text("NVIDIA_API_KEY=saved-key\nDEEPSEEK_API_KEY=active-key\n")
    originals = (config.read_bytes(), env.read_bytes())
    monkeypatch.setattr(model_switch, "list_authenticated_providers", lambda **_: [
        {"slug": "nous", "name": "Nous Portal", "models": ["existing-model"], "is_current": True},
        {"slug": "deepseek", "name": "DeepSeek", "models": [], "is_current": False},
        {"slug": "custom:private", "name": "我的接口", "models": [], "is_current": False},
    ])
    monkeypatch.setattr(inventory, "_local_runtime_row", lambda _: None)
    monkeypatch.setattr(inventory, "_moa_provider_row", lambda _: None)
    payload = inventory.build_models_payload(inventory.load_picker_context(), include_unconfigured=True)
    rows = {r["slug"]: r for r in payload["providers"]}
    assert "nous" not in rows
    assert rows["deepseek"]["name"] == "深度求索"
    assert rows["custom:private"]["name"] == "我的接口"
    keys = config_env._get_env_vars_sync()
    assert keys["NVIDIA_API_KEY"]["category"] == "custom"
    assert keys["DEEPSEEK_API_KEY"]["provider_label"] == rows["deepseek"]["name"]
    assert "COPILOT_GITHUB_TOKEN" not in keys
    assert load_config()["nous"]["guest"] is False
    assert (config.read_bytes(), env.read_bytes()) == originals
