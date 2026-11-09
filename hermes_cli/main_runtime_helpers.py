"""Shared runtime startup helpers for the desktop and administrative commands."""
import contextlib


def sync_bundled_skills_quietly():
    with contextlib.suppress(Exception):
        from tools.skills_sync import sync_skills
        sync_skills(quiet=True)
