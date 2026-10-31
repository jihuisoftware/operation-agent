# Desktop Engineering Guide

Inherits the repository `AGENTS.md`; product scope, TypeScript conventions, contribution rules and
shared test policy are defined there. Read `src/AGENTS.md` for renderer/backend contracts and
[DESIGN.md](./DESIGN.md) for UI changes. [ENGINEERING.md](./ENGINEERING.md) holds explanations and
examples: read the section relevant to the task. Feature entry points: [code map](../../docs/code-map.md).
When code and guidance disagree, verify intent and fix the inconsistency without breaking invariants.

## Ownership and state

- Electron owns machine/process lifecycle, native filesystem/git/windows, install/update and a narrow
  typed capability bridge. The renderer never reaches Node/Electron through a general escape hatch.
- The renderer owns presentation and ephemeral interaction; the agent backend owns sessions, tools,
  model calls and streaming. Desktop is a native chat surface, not the browser dashboard or embedded TUI.
- Backend data is authoritative across surfaces; renderer copies are caches. Electron owns runtime
  facts. Use feature stores for shared UI state, the query layer for request-shaped data, component
  state for local interaction, and refs for coordination that must not paint. Earn new global stores.
- Persisted keys declare their scope: connection, Profile, session, project, window or explicitly global.
  Distinguish durable/runtime/lineage-root session identities and translate at boundaries.
- `prompt.submit` durably writes the session and user rows; the turn adopts them without duplicating.
  New Profile-keyed localStorage families join BOTH `migrateTilesForProfile` and `dropTilesForProfile`.
  `goneSessionVerdict` → `'draft'` adopts unsent text once, without toast, navigation or focus steal.
- Merge server state; optimistic updates roll back visibly. Stale async results must not overwrite
  newer intent; only the foreground surface publishes into shared views. Coalesce cosmetic updates,
  flush terminal transitions, and preserve reference identity on no-ops.

## Connections, recovery and isolation

- Connection/mode changes are soft re-homes: keep the shell, explicitly clear gateway-bound stores,
  reconnect. Runtime `HERMES_HOME` changes require reload. Profile swaps retain background streams;
  the active socket, Profile and connection atoms must agree after every swap.
- Each resolver has one ordered precedence path across local/remote/cloud, versions and Profiles.
  Probe candidates before trusting them. A failed read may fall through; a failed authoritative write
  must surface or visibly roll back. Distinguish missing capabilities from transient failure; retries
  are bounded and end with a recovery action.
- OAuth gateway connections mint fresh tickets on every dial; only confirmed 401/403 means reauth.
  Connection tests probe the actual leg used. `persist:` partitions avoid Electron's percent-escaped
  names (`electron/oauth-partition.ts`).
- Desktop/runtime versions update separately: compatibility fallbacks preserve the feature, target
  an identified older runtime and have a test. Do not silently degrade capability.

## Guest security and capability boundaries

- Guest content never opens the OS browser itself (GHSA-9f4c-93c8-jc8g): `setWindowOpenHandler` denies
  everything; webviews have no `allowpopups`. Guest `target="_blank"` reaches `hermes:openExternal`
  only via the `persist:hermes-preview` trusted-click preload bridge, HTTP(S) only. Preserve the
  partition, trusted-click and scheme gates; see ENGINEERING.md for the advisory context.
- Shell registries are composition seams, not a public plugin ABI. Do not invent a universal extension
  system, manifest or adapter for one consumer; shared contracts need multiple real consumers.
  Different Hermes plugin kinds do not automatically share one surface model.
- Agent-callable renderer capability belongs to the session client: use `session.create`'s
  `source: 'desktop'`, never a backend-host env var. The gateway may be remote/cloud; see
  `tools/AGENTS.md` for session surface availability.

## Interaction and performance

- Background events never navigate, open panes or steal focus. Offer actions instead.
- Distinguish empty, loading, reconnecting, stale/degraded and exhausted recovery states with useful
  copy and a way forward. Focused surfaces own keyboard input; one cancel gesture does one thing.
- Hidden terminals and live tools stay mounted. Visibility is not lifecycle.
- Keep hot-path state local or narrowly derived; do not subscribe heavy trees to per-frame updates.
  Coalesce pointer work, avoid layout reads after style writes and expensive mounts mid-gesture.
  Validate with realistic long transcripts; remove motion that masks latency.

## Verification

Use the root testing policy. Exercise real ownership/routing boundaries, resolver failure paths,
optimistic rollback, stale responses and both local/remote adapters. Before handoff verify focus,
recovery, persistent scope and hot-path performance; use DESIGN.md's checklist for UI changes and
update all supported locales. Backend launch, slash palette and free-tier contracts live once in
[src/AGENTS.md](src/AGENTS.md); longer reasoning stays in ENGINEERING.md.
