"""Managed configuration and the operations build scope, before caching."""

from __future__ import annotations

from typing import Any


def merge_managed_config(expanded: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    """Apply the managed-scope overlay; returns ``(merged, managed_config_or_falsy)``.
    Managed wins at the leaf and is applied AFTER user expansion so a user ``${VAR}`` cannot shadow
    a managed literal: managed values expand only against the process environment. This
    deliberately inverts the usual env-over-config precedence for the keys the managed layer pins
    (docs/design/managed-scope.md §4.1)."""
    from hermes_cli import config as cfg
    from hermes_cli.operations_profile import apply_operations_profile
    managed_config = cfg.managed_scope.load_managed_config()
    if not managed_config:
        return apply_operations_profile(expanded), managed_config
    # Same canonicalization as the user config BEFORE merging (parity with
    # cfg.managed_scope.apply_managed_overlay) so the merged result never exposes a nested dict.
    managed_normalized = cfg._normalize_root_model_keys(managed_config)
    if isinstance(managed_normalized.get("model"), str):
        managed_normalized = dict(managed_normalized)
        managed_normalized["model"] = {"default": managed_normalized["model"]}
    return apply_operations_profile(cfg._deep_merge(expanded, cfg._expand_env_vars(managed_normalized))), managed_config

