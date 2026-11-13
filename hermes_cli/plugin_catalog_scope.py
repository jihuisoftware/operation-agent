"""Operations catalog discovery policy; installation and migration keep full resolution."""

from __future__ import annotations

from hermes_cli.operations_profile import OPERATIONS_PROFILE


def catalog_entry_visible(entry, *, platform=None) -> bool:
    """Apply the product's target platform and curated shelves to local or live entries."""
    policy = OPERATIONS_PROFILE["pluginCatalog"]
    from hermes_platform.host.facts import os_family
    platform = platform or os_family()
    if entry.platforms and platform not in entry.platforms:
        return False
    if entry.category == "platform" or entry.name in policy["exclude"]:
        return False
    return entry.category in policy["categories"] or entry.name in policy["include"]


def browse_catalog(entries):
    """Filter after source resolution so remote refresh cannot bypass product scope."""
    return [entry for entry in entries if catalog_entry_visible(entry)]
