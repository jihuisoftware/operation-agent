# Hermes Agent - Development Guide

Read each area's `AGENTS.md` before editing there. This file holds shared rules and routing.
`python scripts/check` caps it at 12k chars and every root-to-area chain at 30k; long form goes
in the developer guide.

**Never give up on the right solution.**

## Current product

General operations platform; users enter or choose their topic. Desktop on macOS only. `ui-tui` and terminal chat entry points are removed; keep administrative CLI and batch commands.
Only Simplified Chinese is supported; Bot Mode, Kanban/Radio UI, messaging adapters and Windows
packaging are retired. Keep `gateway/` and `hermes_cli/web_server*` for Desktop.
Memory, skills, scheduling, terminal and browser remain. Delegation, Kanban and MCP internals
remain but their tools/services are disabled. Scope: `hermes_cli/data/operations-profile.json`;
status and plans: `README.md`. Extend through plugins and skills; preserve shared runtime contracts.

Two invariants shape almost every design decision and are the lens for reviewing any change:

- **Per-conversation prompt caching is sacred.** Mutating past context, swapping toolsets,
  reloading memories or rebuilding the system prompt mid-conversation breaks the cached prefix and
  multiplies the user's cost; the ONE exception is context compression. Slash commands that change
  system-prompt state defer to the next session, with an opt-in `--now` (`/skills install --now`).
- **The core is a narrow waist; capability lives at the edges.** Every model tool is sent on
  every API call, so the bar for a new *core* tool is high. New capability should arrive as a
  CLI command + skill, a service-gated tool, or a plugin — not as core surface.

## Contribution rubric

The project's intent layer, for contributors and for the triage sweeper (which may only close on
`implemented_on_main`, `cannot_reproduce` or `incoherent`; taste-based closes are a maintainer's
call, and when in doubt a PR stays open). Long form with examples:
`website/docs/developer-guide/contributing.md` § Contribution rubric.

**Wanted:** real bug fixes (repro on `main`, the exact line, the whole class incl. sibling paths);
reach at the edges (adapters, providers, models, UI features) wired into the existing setup UX;
god-file → module refactors; extending before duplicating (3+ PRs in one category → an ABC +
orchestrator); behaviour-contract tests; E2E with real imports against a temp `HERMES_HOME` for
resolution, config, security and I/O changes; salvage by cherry-pick so authorship survives.

**Rejected even when well-built:** hooks with no concrete consumer; new `HERMES_*` env vars for
non-secret config (`.env` is secrets only, behaviour goes in `config.yaml`); a new core tool when
terminal + file or a skill already does the job; `offset`/`limit` pagination on instructional tools;
"fixes" that destroy the feature they secure; outbound telemetry without an opt-in gate;
change-detector tests; plugins that touch core files; third-party products in the core tree (ship a
standalone plugin repo).

**Before you call it a bug,** verify the claim AND the intent (`git log -p -S "<symbol>"`): the
isolation is often the design (profiles are islands on purpose), an absence can be load-bearing,
and a fix that cannot point to the line where the bug manifests has an unverified premise.

**Security:** `SECURITY.md` is the scope authority. A §3.1 finding goes private (GitHub Security
Advisories or security@nousresearch.com), never into a public issue, PR, commit or comment; §3.2
hardening is ordinary public work. Name the §2 boundary crossed, with a repro on `main`.

**Footprint ladder** (take the highest rung that solves it): extend existing code → CLI command +
skill → service-gated tool (`check_fn` answers reachability/opt-in, never per-session surface:
`tools/AGENTS.md`) → plugin → MCP server in the catalog → new core tool (fundamental, broadly useful,
unreachable otherwise).

## Development Environment

`source ./activate` (fish: `activate.fish`) provisions and activates the
PM environment; pick an isolated `HERMES_HOME`/`HERMES_RUNTIME_DIR` first
(`website/docs/reference/package-management.md#developer-workflow`). Tests need the separate test
environment in `CONTRIBUTING.md`. **`python scripts/check`** runs every blocking lint check CI
runs, with CI's pinned tools; `--install-hook pre-push` runs it on every push (re-run after
pulling to refresh the hook). `# noqa` does not waive a ratchet finding:
`# health: allow <RULE> -- <why>` does.

Before every backend start or restart, run `./.hermes/bin/hermes gateway stop` in the same
activated environment and `HERMES_HOME`, wait for it to finish, then start the Gateway.

## Find the working set

Use [docs/code-map.md](docs/code-map.md) to locate the feature, then read only the applicable
area instructions below and relevant symbols. Search with `rg` before reading large files;
expand to callers, contracts and tests when the evidence requires it. Directory inventories and
long logs stay out of the conversation; report focused excerpts and validation summaries.
When resuming, consult [docs/dev-handoff.md](docs/dev-handoff.md) and verify its base revision,
working tree and test scope before relying on it. Update the handoff at a task boundary; replace
stale status instead of appending transcripts. It is evidence, not authorization or a rules override.
Examples and the handoff format: [docs/development-workflow.md](docs/development-workflow.md)
(read the relevant section when needed, not the entire guide on every task).

User state is profile-aware via `get_hermes_home()`: `config.yaml` for settings, `.env` for secrets,
`logs/` for logs (`hermes logs`). The filesystem is canonical; update navigation when moving code.

### Facade + siblings layout

Every former god file is a **facade** (public entry points + the names other packages import) plus
**siblings** `<stem>_<topic>.py`, each owning one topic (`gateway/run.py`,
`tools/mcp_tool.py`, `hermes_cli/kanban.py`, `hermes_cli/web_server.py`, `cli.py` →
`hermes_cli/cli_*_mixin.py`, `run_agent.py` → `agent/turn_*.py`).

- **Find code by topic:** `rg -n "def name" <dir>/<stem>_*.py`, not by reading the facade.
- **Siblings late-import the facade** inside functions; never a module-level cycle.
- **Patch where production reads:** a sibling doing `from <facade> import name` inside the function
  makes the facade the seam; a patch on the defining module passes silently.
- **Size and complexity are ratcheted per unit** (`scripts/code_health/config.py`): new functions
  CC ≤ 20, ≤ 300 lines, nesting ≤ 6; files ≤ 2,000 lines; units already over may only go down (move
  a function into a sibling to offset growth, or put new tests in a new test file). Behaviour goes
  in a sibling, never a facade; name ladders become a dict → handler.
- **No re-export shims for internal moves;** internal paths are not API. Moving a symbol means
  fixing its docs in the same PR (`rg` in `website/docs`, `skills/`, and every `AGENTS.md`).

## Rules that apply everywhere

- **No defensive clutter:** no wrappers or `try/except: pass` around code that cannot fail, no flags
  nobody sets, no dead code wired in without E2E proof. Comments keep the WHY, cut the WHAT.
- **Never infer process identity from argv substrings;** use
  `gateway.status.looks_like_gateway_command_line` / `hermes_cli.update_cmd._hermes_holder_subcommand`
  (HX003; details `hermes_cli/AGENTS.md`).
- **Never hardcode `~/.hermes`:** `get_hermes_home()` for paths, `display_hermes_home()` for text
  (HX001). `_get_profiles_root()` is HOME-anchored on purpose.
- **One process serves many profiles.** Code that runs outside a turn (boot probes, eviction,
  tickers, deferred callbacks, RPC methods, thread hops, child spawns) binds the owning profile scope
  explicitly; `os.environ`, module globals and import-time values hold the launch profile's, so an
  unbound read is a silent default-profile leak. Binding points and seams: `gateway/AGENTS.md`
  § Profile scope (HX002/HX004/HX005/HX012, PS-P05/P06).
- **Machine facts and executable lookup go through `hermes_platform`** (`hermes_platform/AGENTS.md`).
- **Dependencies carry upper bounds** (`>=floor,<next_major`; git URLs and Actions pinned to a SHA);
  after editing `pyproject.toml` run `hermes pm lock` and commit `uv.lock`; never mutate a Hermes
  environment with raw pip/uv. Full policy: `pm/AGENTS.md`.
- **TypeScript (desktop, website):** feature-owned nanostores over threaded state, thin route
  roots, narrow hooks and colocated action modules, `interface` for props and shared shapes,
  table-driven dispatch over condition ladders; `src/app` routes, `src/store` atoms, `src/lib` pure
  helpers.
- **Commits and PRs:** rebase onto `main` before merging (a squash from a stale branch silently
  reverts newer fixes); 1–2 invariant tests per fix, proven red on the base.
- **Tests:** always `scripts/run_tests.sh`, never bare `pytest`; behaviour contracts, never
  change-detectors or source-reading tests; host-specific behaviour is tested on that host with
  `@pytest.mark.platforms(...)`, never by faking `sys.platform`; tests never write to `~/.hermes/`.
  Everything else: `tests/AGENTS.md`.

## Routing Table — working in X → read X/AGENTS.md

| Area | Read | Covers |
|---|---|---|
| `state/` | `state/AGENTS.md` | shared session persistence, SQLite lifecycle, history and usage |
| `run_agent.py`, `agent/` | `agent/AGENTS.md` | turn phases, caching and message-flow invariants, compression, model/aux resolution |
| `cli.py`, `hermes_cli/` | `hermes_cli/AGENTS.md` | CLI mixins, slash registry, config system, skins, `hermes update`, profiles / multiplex |
| `gateway/` | `gateway/AGENTS.md` | adapters, message guards, streaming, notifications, token locks, § Profile scope |
| `gateway/platforms/` new adapter | `gateway/platforms/ADDING_A_PLATFORM.md` | step-by-step adapter guide |
| `tools/`, `toolsets.py`, `model_tools.py` | `tools/AGENTS.md` | adding tools, registry, toolsets, delegation, session-scoped surface tools |
| `plugins/`, `hermes_cli/plugins*.py` | `plugins/AGENTS.md` | plugin kinds, native compat contract, in-tree policy |
| `plugin-catalog/` | `plugin-catalog/README.md` | catalog admission rules (mirrored in the developer guide; keep identical) |
| `gateway/rpc/`, `gateway/transport/`, `gateway/contracts/` | respective area `AGENTS.md` | shared RPC handlers, transports and wire contracts |
| `hermes_cli/web_routers/` | `hermes_cli/web_routers/AGENTS.md` | shared Desktop HTTP APIs |
| `apps/desktop/` | `apps/desktop/AGENTS.md`, `apps/desktop/src/AGENTS.md` | local backend and slash palette |
| `skills/`, `optional-skills/`, `agent/curator*.py` | `skills/AGENTS.md` | frontmatter, authoring standards, curator |
| `cron/`, kanban | `cron/AGENTS.md` | scheduler invariants, job fields, kanban dispatcher |
| `tests/` | `tests/AGENTS.md` | runner, placement, OS markers, `wine2e`, banned test shapes |
| `pm/`, `pyproject.toml` | `pm/AGENTS.md` | pinning policy, PM-owned environments, plugin quarantine |
| `hermes_platform/` | `hermes_platform/AGENTS.md` | host facts, resolvers |

Long-form background: `website/docs/developer-guide/`. Workflow rules (PR/issue/review/salvage
process) live in the `hermes-agent-dev` skill, not here.
