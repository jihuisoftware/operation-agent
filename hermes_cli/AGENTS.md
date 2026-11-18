# hermes_cli/ — management commands and shared application services

Applies on top of the root [AGENTS.md](../AGENTS.md). Start with the [responsibility map](README.md).

## Product boundary and entry points

User conversations run in Desktop; `main.py::cmd_chat` rejects ordinary interactive terminal chat.
Administrative commands, non-interactive queries and shared runtime helpers remain. Do not restore
`--tui`, `--cli`, Ink builds, the old SPA or dashboard PTY chat route. macOS is supported;
Windows x64 packaging is under native validation ([status](../docs/windows-development.md)).

Desktop attaches through `hermes gateway ensure --json`. `gateway_runtime*` and `gateway_client`
handle discovery and connection; `gateway.py` manages lifecycle commands. The process owner and
session authority live in `gateway/`, not in a separate process named after this package.
`gateway/run_api.py` mounts `web_server*` and `web_routers/` for private Desktop HTTP APIs.
Native chat uses `gateway/session_*`; see [Gateway layering](../docs/gateway-rpc.md).

## Shared implementation and facade seams

`cli.py` still holds `HermesCLI`; `cli_*_mixin.py` and topical siblings retain command, single-query,
rendering and compatibility logic. A retained REPL/widget implementation is not an enabled product
entry point. Trace consumers before removing it. Bodies late-bind `cli` names, so tests patch where
production reads; CLI facade globals remain facade-owned and must not be duplicated into siblings.

`gateway.py` is the management facade; `gateway_launchd.py`, `gateway_windows*`,
`gateway_supervised_restart.py` and `gateway_migrate*` own lifecycle topics. Siblings read facade
names through `_gw()`; patch the facade seam. Retained systemd support is compatibility code,
not a declaration of Linux desktop distribution support.

`process_command()` uses `resolve_command()` and `HermesCLI._SLASH_DISPATCH`, with the existing
handler-name fallback; do not add an elif ladder. Skill commands inject a user message from the
owning Profile's skills directory, never rewrite the cached system prompt.

For retained administrative terminal pickers use the existing curses helpers. Desktop forms use
Desktop components. In shared terminal rendering, avoid ANSI erase-to-EOL sequences that leak
through `patch_stdout`; preserve existing display and single-query contracts without restoring a
second chat UI.

## Slash command registry (`hermes_cli/commands.py`)

`COMMAND_REGISTRY` (list of `CommandDef`) is the single source; everything derives from it: CLI
dispatch (`resolve_command()`), gateway `GATEWAY_KNOWN_COMMANDS` + dispatch, `gateway_help_lines()`,
`COMMANDS` (autocomplete),
`COMMANDS_BY_CATEGORY` (`show_help()`). Legacy platform projections remain internal; their existence
does not enable retired messaging entry points. Desktop uses `CommandDef.desktop` plus product filters
and the generated slash registry (see [Desktop instructions](../apps/desktop/src/AGENTS.md)). Fields: `name` (no slash), `description`, `category`
(`Session | Configuration | Tools & Skills | Info | Exit`), `aliases` tuple, `args_hint`,
`cli_only`, `gateway_only`, `gateway_config_gate` (config dotpath; a `cli_only` command becomes
gateway-available when truthy — `GATEWAY_KNOWN_COMMANDS` always includes gated commands so the
gateway can dispatch them; help/menus show them only when the gate is open).

**Choose the consumer before adding a command:** administrative `hermes <subcommand>` parsers
belong in `subcommands/` and dispatch through `main.py`. Shared slash metadata belongs in
`COMMAND_REGISTRY`; set its Desktop disposition and busy behavior explicitly, and regenerate
`apps/desktop/src/lib/desktop-slash-registry.json` with `scripts/dump_desktop_slash_registry.py`
when those fields change. Shared pure command executors use the existing `slash_exec.py` seam;
session-mutating commands use the owning session/control path. Extend a retained CLI or Gateway
handler only when it has an actual consumer; do not create every historical surface by default.

Aliases belong in `CommandDef.aliases`, not duplicated parsers. Configuration writes use the
canonical writer below. Commands changing system-prompt state defer invalidation to the next
session, with an explicit `--now` opt-in where supported (root invariant).

### Shared goal commands

`hermes_cli/goal_command.py::dispatch_goal_command` owns `/goal` parsing and manager
mutations. Supported Desktop and management consumers, and retained compatibility callers,
delegate there; adapters only resolve sessions, authorize gate creation, render
results, and schedule kickoff/continuation prompts. Async callers preserve ContextVars
when running dispatch off-loop (drafting uses profile-scoped auxiliary credentials).
Do not add a surface-specific goal parser or infer a new entry point from this shared implementation.

## Config system (`hermes_cli/config.py`)

- **config.yaml option:** add to `DEFAULT_CONFIG`. Bump `_config_version` ONLY to actively
  migrate/transform existing config (rename keys, restructure); new keys deep-merge automatically.
  Top-level sections (non-exhaustive): `model, agent, terminal, compression, display, stt, tts,
memory, security, delegation, smart_model_routing, checkpoints, auxiliary, curator, skills,
gateway, logging, cron, profiles, plugins, honcho`. `auxiliary` = per-task side-LLM overrides
  ([agent/AGENTS.md](../agent/AGENTS.md)); `curator` = `enabled, interval_hours, min_idle_hours, stale_after_days,
archive_after_days, backup.*`.
- **.env = SECRETS ONLY** (keys, tokens, passwords): add to `OPTIONAL_ENV_VARS` with
  `{"description", "prompt", "url", "password": True, "category": provider|tool|messaging|setting}`.
  Non-secret settings go in config.yaml; if internal code needs an env mirror, bridge it in code
  (`gateway_timeout`; `terminal.cwd` → `TERMINAL_CWD`). `MESSAGING_CWD` is removed and `TERMINAL_CWD`
  in `.env` is deprecated — the loader warns; canonical is `terminal.cwd`. `hermes config
set/get/unset <NAME>` route any bare name registered in `OPTIONAL_ENV_VARS` / `_EXTRA_ENV_KEYS`
  (or carrying a `setup_hidden_env` platform suffix) to `.env` via `config_env_routing.py` — the
  canonical secrets file — never to the top level of config.yaml. This does not re-enable retired platform setup flows.
- **One writer seam.** Every write of a `config.yaml` (main or profile) goes through
  `hermes_cli.config.atomic_config_write` (refuses deletion by omission) or the explicit
  `atomic_config_replace` full-state path (→ `utils.atomic_roundtrip_yaml_save`, ruamel
  round-trip): comments, key order, quoting and blank lines survive, and the fail-closed unreadable-file
  guard runs first. Deliberate `pop()`/unset/migration paths use `atomic_config_replace`; additive
  writers stay on `atomic_config_write`. Never call
  `atomic_yaml_write` / `yaml.dump` / `yaml.safe_dump` on a config path — `scripts/check_config_yaml_writers.py`
  (CI lint) rejects it, and `tests/hermes_cli/test_config_yaml_comment_preservation.py` guards each
  path (#92554). The commented example blocks are appended only when the file is created.
- **Three loaders — know which you're in:** `load_cli_config()` (CLI, `cli.py`); `load_config()`
  (`hermes tools/setup`, most subcommands, `hermes_cli/config.py`, merges `DEFAULT_CONFIG`);
  `hermes_cli/config_effective.py::load_user_config_effective()` (gateway runtime via
  `gateway/run.py::_load_gateway_config`, shared RPC readers, cron, retained command helpers and doctor,
  `hermes_time`/`hermes_logging`: user file + managed overlay + `${VAR}` expansion + model-key
  canon, NO defaults — for presence-sensitive readers). If the CLI sees a key and the gateway
  doesn't (or vice versa), you're on the wrong loader — check `DEFAULT_CONFIG` coverage. Never
  hand-roll raw-read → overlay → expand; `read_user_config_raw` is for write-back round-trips only.
- **Operations scope:** `data/operations-profile.json` feeds `config_overlays.py` and
  `gateway/run_config_loaders.py`; raw/effective reads stay unchanged.
- **Every `DEFAULT_CONFIG` key has a runtime reader, and every reader a registry entry.** Both drift
  modes are silent: a registered key nothing reads (a knob that does nothing) and a reader of a key
  never registered (never shown, never migrated; new roots also go in `_KNOWN_ROOT_KEYS`). For a new
  key: `rg -n '"<key>"' hermes_cli/config_defaults.py` AND `rg -n '<key>' --glob '!tests' .` both hit,
  and one invariant test sets it in a temp `config.yaml` and asserts the behaviour through the loader
  the consuming surface uses. Under multiplex the process env never overrides a profile's YAML.
- **Working directory:** command processes use `os.getcwd()` where applicable; routed execution uses `terminal.cwd`, bridged to
  `TERMINAL_CWD` for child tools.

## Skin engine (`hermes_cli/skin_engine.py`)

Skins are **pure data** (`SkinConfig`); no code change to add one. `init_skin_from_config()` reads
`display.skin` at startup; `get_active_skin()` (cached), `set_active_skin(name)` (`/skin`),
`load_skin(name)` (owning Profile skins directory → built-ins → default; missing values inherit
from `default`). Built-ins in `_BUILTIN_SKINS`: `default`, `ares`, `mono`, `slate`. Keys: `colors.*`
(banner border/title/accent/dim/text, response_border), `spinner.*` (waiting/thinking faces,
thinking_verbs, wings), `tool_prefix`, `tool_emojis`, `branding.*` (agent_name, welcome,
response_label, prompt_symbol). Consumers include retained `banner.py`, `display.py` and `cli.py` helpers.
Use `skin_engine.py` and its tests for the current contract; this does not restore terminal chat.

## Update pipeline (`hermes update`)

Transactional, `plan → snapshot → apply → restart-per-kind → verify → report`; every stage guards a
real field failure (fleet campaign #91277), and a PR that weakens a stage answers for that class.
Trace the current stages through `update_cmd.py` and its `update_*` siblings; preserve the contracts below.

- Snapshots cover EVERY profile with one identical file set (never partial or tiered); they are
  file-loss recovery, `--backup` owns rollback.
- The Windows ZIP fallback fires only when git itself failed, refuses a dirty tree, and grafts the
  `_ZIP_PRESERVED_NESTED` build outputs into the swap.
- Restarts are fleet-wide and drain-first, bounded by the home each unit runs on
  (`update_fleet_scope.py`); another install's runtime is never restarted.
- Post-commit failures are owed follow-ups, exit 0 (stash left 1, Ctrl-C 130);
  receipts in ROOT `logs/update_receipts/`.
- Nothing runs pulled code in the pre-pull interpreter. `update_handoff.py` and
  `update_serve_obligations.py` are a FROZEN compat surface (`tests/compat/old_updater_surface.json`):
  removing a name bricks releases mid-update.
- Use the gateway-owned control socket and canonical process matchers in `gateway/status.py` and
  `update_cmd.py`; never identify a process by argv substrings or bare PID existence.

## Profiles and multiplexed ownership

`_apply_profile_override()` in `hermes_cli/main.py` sets `HERMES_HOME` before any module import for
single-profile commands (`hermes -p x <cmd>`), so there `get_hermes_home()` scopes to the active
profile. The multiplex Gateway serving Desktop and the retained server helpers bind the active
profile per activity via a contextvar override while `os.environ["HERMES_HOME"]` keeps the launch
profile — a module constant or import-time read there freezes to the launch profile (rules in
root). Profiles are independent
islands by design — no live config inheritance; `--clone` copies at creation, minus messaging
channels (`profile_channels.py`: ownership-based inventory evaluated in the SOURCE's plugin scope —
adapter-declared keys + canonical/alias prefixes + `GATEWAY_ALLOW*`/`GATEWAY_RELAY_*`; prefixes shared
with tools (`TWILIO_`/`EMAIL_`, plus a plugin platform's `shared_env_prefixes`) are stripped only when the source runs that adapter; never a hand
list; a platform that left core keeps its ownership from its `LEFT_CORE` row while the plugin is absent). `--clone-channels` opts in and its live-multiplexer refusal lives in `create_profile` (management and shared API callers go through it). Clones are built in `profiles/.<name>.staging-<pid>` (hidden → invisible to
`_iter_named_profile_dirs` and the hot-serve rescan) and published by one `os.rename` after the strip;
symlinked `.env`/`config.yaml` are materialized first so a clone never writes through to its source. Multiplex
(`gateway.multiplex_profiles`) secret-scope rules: `gateway/AGENTS.md`. The served set is
`profiles.py::profiles_to_serve(multiplex=True)` = default + every live dir under `profiles/` — live =
carries an identity marker (`hermes_constants.named_profile_has_identity`: `config.yaml`/`.env`/`SOUL.md`/
`profile.yaml`/`auth.json`/`state.db`) and is not tombstoned. A marker-less dir (cron/log side-effect
shell, stray infrastructure dir) is never listed, served, ticked, `.env`-backfilled or resolvable via `-p`
(#95188, #99392); `profile create` replaces it only when it is also tombstoned (a live marker-less dir may hold user
files — fail closed, never rmtree). A dangling symlinked marker still counts as identity (`is_symlink()`).
`tools/bot_mode_probe._roster` (Bot Mode teammate roster, `bot_relay.deliver` target check) applies the same
predicate. There is no allowlist (`gateway.multiplex_profile_allowlist` was retired in config v43).
Enumeration is a pure read: never `mkdir` a profile home from a served path (`SessionDB`, logging,
cron all go through `mkdir_under_hermes_home` / `_ensure_cron_dir`, which refuse a deleted or
missing named profile, #94590). Process-global per-profile slots (MCP discovery in `mcp_startup.py`,
tool registry overlays) key on `hermes_constants.hermes_home_key()`, never a single flag.
`gateway.multiplex_profiles` defaults to **on**, but `GatewayConfig` keeps an unset flag `None` and
`gateway_multiplex_mode.resolve_multiplex_mode` settles it once per boot (called from
`load_gateway_config_for_runner`): default profile, >= 2 profiles, no standalone secondary gateway,
no preflight blocker, migratable host → `True`; else `False` + a logged reason. Explicit values pass
through. Management and Desktop HTTP readers use `default_gateway_multiplexes` (live `served_profiles` record, then
the explicit flag) — never the merged default, which would guess a verdict only the gateway makes.
Migration from per-profile gateways: `hermes_cli/gateway_migrate.py` (`hermes gateway migrate
--multiplex`, the only mode — `--standalone` is deleted and a per-profile fleet is not a supported
target; table-driven `_PREFLIGHT_CHECKS`; manifest `<default>/gateway_migration.json` = UNFINISHED,
a re-run resumes from it; a named profile's `gateway install|start|run` refuse without `--force` via
`gateway.py::_named_profile_refused_under_multiplexer`, dashboard twin
`web_server_gateway.py::multiplexed_profile_refusal`);
`update_cmd_fleet_verify._verify_fleet_after_update` calls `maybe_auto_migrate_after_update` on the success
path only; `gateway_migrate_guards.py` holds the auto-path-only refusals (table `_AUTO_MIGRATION_GUARDS`:
other service domain / UNIX user / HERMES_HOME outside `profiles/` — notices for the explicit command,
blockers for the hook) and the `gateway.auto_multiplex_migration` opt-out (#109954). Blockers reuse `GatewayRunner._adapter_credential_fingerprint` and `platform_binds_port`;
"has a `/p/<profile>/` ingress" is the adapter class attribute `serves_profile_prefix` — set it on a
new HTTP-inbound adapter when it answers the prefix, never extend a list here.
`hermes gateway restart` for a gateway Hermes did not install (custom launchd agent / unit running
`gateway run --external-supervisor`): `gateway_supervised_restart.py` — the gateway's SELF-declared
supervisor (control-socket `identify` answering anything but `manual`, OR the argv marker) decides; hand back via SIGUSR1 and wait
for a fresh supervised PID, never stop + foreground `run_gateway` (that stamps the CLI's PID and wedges
every KeepAlive respawn, #110637).

Service installs are a matrix, not a unit file: `gateway.py::generate_systemd_unit(system=,
run_as_user=)` (systemd unit generation / `systemd_unit_is_current` / `refresh_systemd_unit_if_needed` are PM-aware facade owners; user unit AND `--system` unit with `User=`; an unresolvable `User=` is a blocker,
never a dir-owner fallback), `gateway_launchd.py::generate_launchd_plist` (`gui/<uid>` then `user/<uid>` domains, never a
`~/Library/LaunchAgents` glob; the whole launchd backend — plist refresh, `launchctl` bootstrap/kickstart,
`launchd_start/stop/restart/status`, detached-process degrade — lives in that sibling, with the domain cache
`_resolved_launchd_domain` staying a facade global), Windows Scheduled Task and runtime launch helpers all carry the
profile's `HERMES_HOME` (and `HOME` for the service user) explicitly — a supervisor starts with an
empty environment, so the env override that makes `-p` work interactively does not exist there. A
change to install/restart/status regenerates and diffs every kind; both user and system units are
recorded when both exist. Process liveness is `(pid, start_time)` or the canonical matchers
(`gateway.status.live_gateway_pid_for_home`), never bare PID existence.

## Retained Nous sign-in contract (`hermes_cli/anon_auth.py`)

`anon_auth.run_sign_in()` is the one sign-in composition: it yields `SignInState`s that carry their
own `.copy` / `.copy_terminal`, persists only after a completed promotion AND a token grant, and runs
`settle_after_upgrade` exactly once per completion. `hermes auth upgrade`, the CLI and gateway
`/login` and the desktop poller are renderers over it; the desktop's plain device-code login
(`_nous_plain_poller`) stays a separate path. Provider/product gates still decide what is exposed;
preserving this contract does not enable the operations build’s disabled guest/free-tier entry.
