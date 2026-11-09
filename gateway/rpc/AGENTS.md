# gateway/rpc/ — shared Desktop RPC handlers

Inherits root and gateway/AGENTS.md. Architecture and detailed contracts: [RPC guide](../../docs/gateway-rpc.md).

- `server.py` is the facade; `methods_*.py` and topical siblings own behavior. `method_ctx.bind_module` binds their functions to the facade globals. Patch where production reads, not the defining sibling.
- Session ownership, durable admission and execution stay in `gateway/session_*.py`. This package supplies auxiliary handlers and shared projections, not a second session authority for canonical clients.
- WebSocket/stdio, events and approval delivery live in `gateway/transport/`; schemas in `gateway/contracts/`; profile launch scope and independent helpers in `gateway/runtime/`.
- Every off-turn/profile-scoped read binds home, secrets and terminal scope together. Timer callbacks and shutdown retain the session's profile; never borrow launch-profile credentials.
- Do not mutate a conversation's cached prompt, toolset or memory when moving handlers. Cosmetic/config changes remain deferred according to the existing session policy.
- Keep wire names, source values, HERMES_TUI_* compatibility inputs and existing crash-log names unless a separate behavior migration is authorized. Python import paths are internal; no forwarding `tui_gateway` package.
- Removed terminal-only RPCs `pet.cells` / `learning.frames` return unknown-method. Their rendering code and the PTY back-WebSocket publisher are retired. Keep Desktop pet sprites/metadata, approvals, event replay and internal stdio.
- Verify via `scripts/run_tests.sh tests/gateway/rpc/ tests/gateway/contracts/`. Regenerate shared TypeScript/OpenRPC using `scripts/gen_gateway_contracts.py` after schema changes, then run Desktop/shared checks.
