# apps/desktop/src/ — backend contract and slash palette

Applies on top of `apps/desktop/AGENTS.md` (the judgment guide) and the root `AGENTS.md`.
Root TypeScript style rules apply.

This operations build shares its scope with `hermes_cli/data/operations-profile.json` through
`lib/operations-profile.ts`. Bot Mode, Kanban, Radio and the retired agents/starmap/webhooks/session-import pages are removed.
Keep the product filters to prevent saved configuration or external plugins from reviving retired entry points.

## Desktop local execution belongs to the canonical gateway

Electron + React + nanostores (`@assistant-ui/react`) talks JSON-RPC over the existing
`@hermes/shared` client. Normal local primary and pooled launches invoke
`hermes gateway ensure --json`, consume its credential-free endpoint, and authenticate
WebSockets with fresh private control tickets. The app never acquires the gateway PID as
an owned child. Closing, switching or evicting a Desktop connection disconnects the viewer;
only explicit gateway lifecycle commands stop the owner.

Native tickets cross the private preload IPC transiently, are removed from the URL before
WebSocket construction, and are offered as subprotocols. Electron removes Origin only for
an unexpired one-use dial bound to the requesting window. No public dashboard token is
scraped or added to the public connection descriptor. SSH/URL intent retains its existing
remote resolution and exposure lifecycle; a remote failure must never start a local owner.

The gateway `gateway ensure` attaches to is **one multiplexing owner per home**: `HERMES_DESKTOP=1`
is not how the app finds it, and no per-profile `hermes serve --port 0` child is spawned. One
gateway process serves sessions from several homes (`tui_gateway/AGENTS.md` § Profile scope); a
served secondary answers through the multiplexer's control socket (`GatewayEndpoint.multiplex_home`).
Remote connections (SSH, URL+token, Cloud) likewise reach a backend that may serve several profiles
from one process. Every lifecycle/status/settings REST call carries `?profile=` (or the `profile`
param) and every new-session tile records an owner route; a backend-side scope fix is probed twice —
with the profile as the gateway's own launch home and as a secondary served by one process.

This migration requires the runtime's canonical GUI creation policy and a private HTTP
API credential path. Do not bypass missing runtime capabilities by relabeling GUI sessions
as CLI, dropping launch options, or falling back to an independent local serve owner.

## Slash commands: curated client-side, dispatched to the backend

- The backend already provides everything: `commands.catalog` and `complete.slash` include built-ins,
  user `quick_commands`, AND skill-derived commands. No new RPC is needed to see skills.
- `src/lib/desktop-slash-commands.ts` is the load-bearing file: `DESKTOP_COMMAND_SPECS` (built-ins
  and their desktop surfaces) + the block-list. A command's desktop disposition (terminal-only /
  messaging-only / settings-owned / advanced / hidden) is authored ONCE, as `desktop=` on its
  `CommandDef` in `hermes_cli/commands.py`; the live `commands.catalog` carries it, and
  `src/lib/desktop-slash-registry.json` (regenerate with `scripts/dump_desktop_slash_registry.py`;
  `tests/hermes_cli/test_desktop_slash_registry.py` + the vitest file fail on drift) is the offline
  fallback. Only names the Python registry has never heard of (`/density`, `/details`, `/logs`,
  `/mouse` — Ink-local; `/pets`) live in `TS_ONLY_NO_DESKTOP_SURFACE`. `isDesktopSlashCommand(name)`
  gates **execution** (true
  for built-ins AND any non-built-in so typed skill/quick commands run);
  `isDesktopSlashSuggestion(name)` gates **discovery** — used by BOTH completion paths in
  `app/chat/composer/hooks/use-slash-completions.ts` and by `filterDesktopCommandsCatalog`;
  `isDesktopSlashExtensionCommand(name)` is true for anything not a known built-in, and both
  suggestion and catalog paths let extensions through (the allow-list once silently dropped every
  skill/quick command from completions even though they executed when typed).
- Dispatch: `app/session/hooks/use-prompt-actions/slash.ts` (`runSlash`) — desktop-owned built-ins
  (`/skin`, `/help`, `/new`, ...) locally or via `commands.catalog`; everything else `slash.exec` →
  `command.dispatch` fallback; a skill command resolves to `{type: "skill", message}` and is
  submitted as a normal prompt.

**Rule:** palette curation hides noise (terminal-only / messaging-only built-ins), NEVER
user-activated extensions. If you tighten `desktop-slash-commands.ts`, keep
`isDesktopSlashExtensionCommand` flowing into both paths. Test: from `apps/desktop`,
`npx vitest run src/lib/desktop-slash-commands.test.ts` (workspace deps install at the repo root).

## Free tier surfaces (`src/store/free-tier*.ts`, Billing, statusbar chip, onboarding ready screen)

`$freeTierStatus` mirrors `free_tier.status` (pull; refreshed with the status snapshot and after a
sign-in). `deriveBillingView` branches on `billing.free_tier_account` BEFORE `logged_in` (status
`free_tier`: notice + one Sign in, Plan/Model/Connectors summary, no payment or usage rows); the
`logged_out` notice's Sign in opens the same dialog, never a portal link (a link writes no
credential). The sign-in dialog is a single claimed owner (first mount wins, like the
real-profile consent prompt); its states map 1:1 to the poll route's `status` + `reason`. Copy is the ruled free-tier copy: never
"guest", "anonymous", "claim" or "Nous Portal" in user-facing text.
