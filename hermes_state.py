"""Frozen import for already-running pre-PM updaters; application code uses state.store.

Only SessionDB is part of tests/compat/old_updater_surface.json. Keep that historical
upgrade contract while all storage implementation and current callers live in state/.
"""

from state.store import SessionDB

__all__ = ["SessionDB"]
