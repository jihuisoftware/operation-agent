"""Operations provider discovery and labels; runtime identities remain unchanged."""

from hermes_cli.operations_profile import OPERATIONS_PROFILE

HIDDEN_MODEL_PROVIDERS = frozenset(OPERATIONS_PROFILE["modelProviders"]["hidden"])
MODEL_PROVIDER_LABELS = OPERATIONS_PROFILE["modelProviders"]["labels"]


def provider_label(slug: str, fallback: str = "") -> str:
    return MODEL_PROVIDER_LABELS.get(slug.strip().lower(), fallback or slug)


def scope_provider_rows(rows: list[dict]) -> list[dict]:
    """Filter discovery, including saved credentials, without rewriting their configuration."""
    return [
        {**row, "name": provider_label(str(row.get("slug", "")), row.get("name", ""))}
        for row in rows
        if str(row.get("slug", "")).strip().lower() not in HIDDEN_MODEL_PROVIDERS
        and str(row.get("provider_id", "")).strip().lower() not in HIDDEN_MODEL_PROVIDERS
    ]
