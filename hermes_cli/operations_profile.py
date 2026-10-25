"""Build-wide pet-community scope, layered at config reads without rewriting user data.

The JSON is also consumed by Desktop. Model credentials, memory, history and
user-disabled tools survive; an old generic configuration cannot start retired services.
Changes take effect on process restart and new conversations.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

OPERATIONS_PROFILE = json.loads(
    (Path(__file__).parent / "data" / "operations-profile.json").read_text(encoding="utf-8-sig")
)
DISABLED_TOOLSETS = frozenset(OPERATIONS_PROFILE["disabledToolsets"])


def _overlay(target: dict, values: dict) -> None:
    for key, value in values.items():
        if isinstance(value, dict):
            if not isinstance(target.get(key), dict):
                target[key] = {}
            _overlay(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def apply_operations_profile(config: dict) -> dict:
    """Apply the product scope to an owned config mapping; never write config.yaml."""
    from agent.skill_utils import parse_config_string_list

    _overlay(config, OPERATIONS_PROFILE["settings"])
    agent = config["agent"]
    agent["disabled_toolsets"] = sorted(
        DISABLED_TOOLSETS | set(parse_config_string_list(agent.get("disabled_toolsets")))
    )
    plugins = config["plugins"]
    plugins["disabled"] = sorted(
        set(OPERATIONS_PROFILE["disabledPlugins"])
        | set(parse_config_string_list(plugins.get("disabled")))
    )
    if not isinstance(config.get("platform_toolsets"), dict):
        config["platform_toolsets"] = {}
    selections = config["platform_toolsets"]
    for platform in ("cli", "cron"):
        # Preserve explicit choices, including [] (no tools). The global disabled
        # list still removes retired tools from an old composite selection.
        selections.setdefault(platform, list(OPERATIONS_PROFILE["toolsets"]))
    if not isinstance(config.get("platform_hints"), dict):
        config["platform_hints"] = {}
    hints = config["platform_hints"]
    for platform in ("desktop", "tui", "cli", "cron"):
        hint = hints.get(platform, {})
        if isinstance(hint, str):
            hint = {"append": hint}
        if not isinstance(hint, dict):
            hint = {}
        prior = str(hint.get("append") or "")
        brief = OPERATIONS_PROFILE["brief"]
        if brief not in prior:
            hints[platform] = {**hint, "append": "\n\n".join(filter(None, (prior, brief)))}
    return config
