# hermes_cli/web_routers/ — shared HTTP APIs

Applies on top of the root and `hermes_cli/AGENTS.md` rules.

This branch uses Desktop as the primary interface. The browser dashboard SPA
(`web/`) and its launch entry point have been removed. The shared HTTP/API server
in `hermes_cli/web_server.py` and `web_server_*.py`, these routers, `gateway/rpc/`,
and `apps/shared/` still support Desktop and integrations. Their historical
`web` names do not make them removable frontend code.

- Messaging-account setup and bot pairing APIs are retired. Keep runtime lifecycle,
  Desktop sessions and generic webhook automation; do not restore platform onboarding.
- Keep route handlers in topical router modules; mount them through the existing
  server assembly. Do not grow the server facade with feature-specific logic.
- New REST and WebSocket routes use the existing authenticated connection and
  profile-routing mechanisms. Do not introduce a parallel authentication scheme
  or weaken a route's access checks when removing browser UI.
- Backend state belongs to the served Profile. Resolve profile paths and secrets
  in the active scope, including deferred work and thread/process boundaries.
- Keep Desktop-consumed plugin APIs and connection contracts functional. Extend
  Desktop through its SDK; the retired browser UI plugin SDK is not interchangeable.
- Do not remount an SPA, add a browser dashboard build dependency, or recreate a
  second chat UI here. Desktop chat uses the shared gateway/session machinery.
- Backend route tests belong in `tests/hermes_cli/` and run through
  `scripts/run_tests.sh`; shared RPC contracts also have tests in `tests/gateway/rpc/`.
  Verify authentication, profile isolation, and the actual response contract.

References: `apps/desktop/src/AGENTS.md`, `gateway/rpc/AGENTS.md`, and
`website/docs/developer-guide/desktop-plugin-sdk.md`.
