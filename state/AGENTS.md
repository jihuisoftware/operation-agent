# state/ — shared session persistence

Inherits the root AGENTS.md. Gateway, Agent, administrative CLI and tools share this package.

- `store.py` owns the `SessionDB` / `AsyncSessionDB` facade and its public bindings. Topic siblings
  (`messages.py`, `sessions.py`, `schema.py`, `search.py`, `usage.py`, etc.) own implementation.
- Siblings that depend on the facade import `state.store` inside functions, preserving late binding
  and avoiding module-level cycles. Patch the binding production reads.
- Keep Profile ownership explicit. The database remains `get_hermes_home() / "state.db"`; moving
  Python modules must not move user files, change schemas or rebuild stored conversation context.
- Preserve transactional writes, generation/turn leases, recovery guards and read-only behavior.
  Never weaken a fence to make a storage test pass.
- Tests live in `tests/state/`; run through `scripts/run_tests.sh`. Use isolated homes and real
  SQLite for storage behavior. Current callers use `state.*`; the sole root `hermes_state.py`
  export is the frozen `SessionDB` ABI required by already-running pre-PM updaters
  (`tests/compat/old_updater_surface.json`). Do not add new callers or sibling shims.

Navigation: `docs/code-map.md`. Storage schema and migration declarations live in `schema.py`
and `common.py`; the package move does not change those declarations.
