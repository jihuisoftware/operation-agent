---
sidebar_position: 12
sidebar_label: "Built-in Plugins"
title: "Built-in Plugins"
description: "Plugins shipped with Hermes Agent that run automatically via lifecycle hooks — disk-cleanup and friends"
---

# Built-in Plugins

Hermes ships a small set of plugins bundled with the repository. They live under `<repo>/plugins/<name>/` and load automatically alongside user-installed plugins in `~/.hermes/plugins/`. They use the same plugin surface as third-party plugins — hooks, tools, slash commands — just maintained in-tree.

See the [Plugins](./plugins.md) page for the general plugin system, and [Build a Hermes Plugin](../../developer-guide/plugins/index.md) to write your own.

## How discovery works

The `PluginManager` scans four sources, in order:

1. **Bundled** — `<repo>/plugins/<name>/` (what this page documents)
2. **User** — `~/.hermes/plugins/<name>/`
3. **Project** — `./.hermes/plugins/<name>/` (requires `HERMES_ENABLE_PROJECT_PLUGINS=1`)
4. **Pip entry points** — `hermes_agent.plugins`

On name collision, later sources win — a user plugin named `disk-cleanup` would replace the bundled one.

`plugins/memory/` and `plugins/context_engine/` are deliberately excluded from bundled scanning. Those directories use their own discovery paths because memory providers and context engines are single-select providers configured through `hermes memory setup` / `context.engine` in config.

## Bundled plugins are opt-in

Bundled plugins ship disabled. Discovery finds them (they appear in `hermes plugins list` and the interactive `hermes plugins` UI), but none load until you explicitly enable them:

```bash
hermes plugins enable disk-cleanup
```

Or via `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - disk-cleanup
```

This is the same mechanism user-installed plugins use. Bundled plugins are never auto-enabled — not on fresh install, not for existing users upgrading to a newer Hermes. You always opt in explicitly.

To turn a bundled plugin off again:

```bash
hermes plugins disable disk-cleanup
# or: remove it from plugins.enabled in config.yaml
```

## Currently shipped

The repo ships these bundled plugins under `plugins/`. All are opt-in — enable them via `hermes plugins enable <name>`.

| Plugin | Kind | Purpose |
|---|---|---|
| `disk-cleanup` | hooks + slash command | Auto-track ephemeral files and clean them on session end |
| `security-guidance` | hooks | Pattern-match dangerous code on `write_file`/`patch` and append a security warning (or block) — 25 rules (Apache-2.0 fork of Anthropic's `claude-plugins-official` patterns) |
| `image_gen/openai` | image backend | OpenAI GPT Image 2 and 2.5 Flare/Sunburst generation and editing (API key) |
| `image_gen/openai-codex` | image backend | OpenAI image generation via Codex OAuth |
| `image_gen/xai` | image backend | xAI `grok-2-image` backend |

Memory providers (`plugins/memory/*`) and context engines (`plugins/context_engine/*`) are listed separately on [Memory Providers](./memory-providers.md) — they're managed through `hermes memory` and `hermes plugins` respectively. The full per-plugin detail for the two long-running hooks-based plugins follows.

### disk-cleanup

Auto-tracks and removes ephemeral files created during sessions — test scripts, temp outputs, cron logs, stale chrome profiles — without requiring the agent to remember to call a tool.

**How it works:**

| Hook | Behaviour |
|---|---|
| `post_tool_call` | When `write_file` / `terminal` / `patch` creates a file matching `test_*`, `tmp_*`, or `*.test.*` inside `HERMES_HOME` or `/tmp/hermes-*`, track it silently as `test` / `temp` / `cron-output`. | <!-- no-tmp: ok — documents the plugin's scope guard -->
| `on_session_end` | If any test files were auto-tracked during the turn, run the safe `quick` cleanup and log a one-line summary. Stays silent otherwise. |

**Deletion rules:**

| Category | Threshold | Confirmation |
|---|---|---|
| `test` | every session end | Never |
| `temp` | >7 days since tracked | Never |
| `cron-output` | >14 days since tracked | Never |
| empty dirs under HERMES_HOME | always | Never |
| `research` | >30 days, beyond 10 newest | Always (deep only) |
| `chrome-profile` | >14 days since tracked | Always (deep only) |
| files >500 MB | never auto | Always (deep only) |

**Slash command** — `/disk-cleanup` available in both CLI and gateway sessions:

```
/disk-cleanup status                     # breakdown + top-10 largest
/disk-cleanup dry-run                    # preview without deleting
/disk-cleanup quick                      # run safe cleanup now
/disk-cleanup deep                       # quick + list items needing confirmation
/disk-cleanup track <path> <category>    # manual tracking
/disk-cleanup forget <path>              # stop tracking (does not delete)
```

**State** — everything lives at `$HERMES_HOME/disk-cleanup/`:

| File | Contents |
|---|---|
| `tracked.json` | Tracked paths with category, size, and timestamp |
| `tracked.json.bak` | Atomic-write backup of the above |
| `cleanup.log` | Append-only audit trail of every track / skip / reject / delete |

<!-- no-tmp: ok — documents the plugin's scope guard -->
**Safety** — cleanup only ever touches paths under `HERMES_HOME` or `/tmp/hermes-*`. Windows mounts (`/mnt/c/...`) are rejected. Well-known top-level state dirs (`logs/`, `memories/`, `sessions/`, `cron/`, `cache/`, `skills/`, `plugins/`, `disk-cleanup/` itself) are never removed even when empty — a fresh install does not get gutted on first session end. User project trees (`workspace/`, `projects/`, `plans/`, `home/`) are never tracked or swept at all: a `test_*.py` or `tmp_*` file inside your project is source code, not scratch. `kanban/` (task attachments and workspaces) is never tracked either, and a tracked *directory* under a protected top level such as `cache/` is never removed — only the files inside it age out.

**Enabling:** `hermes plugins enable disk-cleanup` (or check the box in `hermes plugins`).

**Disabling again:** `hermes plugins disable disk-cleanup`.

### security-guidance

Fast pattern-matched security warnings on file writes. When the agent's `write_file` / `patch` / `skill_manage` calls carry content matching a known-dangerous code pattern — `pickle.load`, `yaml.load` without `SafeLoader`, `eval(`, `os.system`, `subprocess(...,  shell=True)`, JS `child_process.exec`, React `dangerouslySetInnerHTML`, raw `.innerHTML =` / `.outerHTML =` / `document.write`, Node `crypto.createCipher`, AES ECB mode, TLS verification disabled, XXE-prone `xml.etree` / `minidom` parsers, `<script src="//..." >` without SRI, `torch.load` without `weights_only=True`, GitHub Actions `${{ github.event.* }}` injection — the plugin appends a `⚠️ Security guidance` block to the tool's result.

The file is still written. The model reads the warning in the next turn's tool message and can either fix the code or document why the construct is safe in this context. Pattern matching has a non-trivial false-positive rate, which is why warn (not block) is the default.

**Coverage:** 25 rules total, covering unsafe deserialization, command injection, XSS sinks, crypto footguns, XXE, supply-chain (SRI), and CI/CD workflow injection. The pattern data is a verbatim Apache-2.0 fork of [Anthropic's `claude-plugins-official`](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/security-guidance/hooks) — see the plugin's `LICENSE` and `NOTICE` files for attribution.

**Modes:**

| Env var | Effect |
|---|---|
| (unset) | **warn mode** (default) — file is written, warning appended to result |
| `SECURITY_GUIDANCE_BLOCK=1` | **block mode** — write refused, warning returned as the block reason |
| `SECURITY_GUIDANCE_DISABLE=1` | kill switch — plugin loads but does nothing |

**Enabling:** `hermes plugins enable security-guidance` (or check the box in `hermes plugins`).

**Disabling again:** `hermes plugins disable security-guidance`.

**What it does not do (yet):** the upstream Anthropic plugin has two more layers — an LLM diff review on each agent turn that touched files, and an agentic commit-time review that traces data flow across files. Neither is ported. The agent can already run those reviews on demand via `delegate_task`.

### Langfuse (moved to the plugin catalog)

Langfuse tracing is no longer bundled with Hermes. It ships as the official
[`langfuse`](https://github.com/NousResearch/hermes-official-plugins/tree/main/langfuse) catalog plugin, with the same hooks, `HERMES_LANGFUSE_*`
environment variables and capture modes:

```bash
hermes plugins install langfuse
```

Profiles that had `observability/langfuse` enabled get the plugin installed and
enabled automatically by `hermes update` (or on the first start after updating),
and keep tracing to the same Langfuse project. Setup, tuning and capture modes
are documented in the [plugin's README](https://github.com/NousResearch/hermes-official-plugins/tree/main/langfuse).

### NeMo Relay native integration (migration note)

NeMo Relay is no longer a bundled Hermes plugin. Do not run `hermes plugins enable observability/nemo_relay`; Hermes core now owns the Relay session, turn, LLM, and tool lifecycles.

Configure Relay middleware or exporters through a standard Relay `plugins.toml`. Hermes loads Relay's user configuration (`~/.config/nemo-relay/plugins.toml`) and then its machine-wide system configuration (`/etc/nemo-relay/plugins.toml`, or `%ProgramData%\nemo-relay\plugins.toml` on Windows). Set `HERMES_NEMO_RELAY_PLUGINS_TOML` before starting Hermes only when you want an explicit file to replace the user configuration; the system configuration still has higher precedence. The policy is process-wide for every profile hosted by that Hermes process. Run `hermes doctor` to see which files apply. See the [NeMo Relay observability configuration](https://docs.nvidia.com/nemo/relay/configure-plugins/observability/about) for ATOF, ATIF, and OpenTelemetry options.

The old `HERMES_NEMO_RELAY_ATOF_*` and `HERMES_NEMO_RELAY_ATIF_*` settings no longer configure exporters. When `HERMES_NEMO_RELAY_PLUGINS_TOML` is unset, the gateway warns about remaining legacy variables and `hermes doctor` reports them. Independently discovered Relay user or system exporters still apply.

**Automatic migration.** `hermes update` (and `hermes migrate relay`, or `hermes migrate relay --all-profiles` for every profile home) converts the legacy variables into `<hermes home>/relay-plugins.toml`, sets `HERMES_NEMO_RELAY_PLUGINS_TOML` in that profile's `.env`, and comments the legacy lines out (nothing is deleted). Under a multiplexed gateway every profile home gets its own file. The generated file is validated through Relay before it is written; this is the shape it produces (note the `type = "file"` sink discriminator — a sink without it is rejected):

```toml
version = 1

[[components]]
kind = "observability"
enabled = true

[components.config]
version = 4
enable_full_payloads = false

[components.config.atof]
enabled = true

[[components.config.atof.sinks]]
type = "file"
output_directory = "/home/you/.hermes/telemetry/nemo-relay/atof"
filename = "hermes-atof.jsonl"
mode = "append"

[components.config.atif]
enabled = true
agent_name = "Hermes Agent"
model_name = "unknown"
output_directory = "/home/you/.hermes/telemetry/nemo-relay/atif"
filename_template = "trajectory-{session_id}.json"

[components.config.opentelemetry]
enabled = false
endpoints = []

[components.config.policy]
unknown_component = "warn"
unknown_field = "warn"
unsupported_value = "error"
```

Then add `HERMES_NEMO_RELAY_PLUGINS_TOML=/home/you/.hermes/relay-plugins.toml` to `.env` and restart the gateway.

#### Session-span segmentation (continuous sessions)

Relay exports a span when its scope closes. A continuous gateway session can keep its session span open for days even though each turn span exports normally. Optional segmentation rotates only the session scope at a turn boundary:

```yaml
gateway:
  telemetry:
    session_segments:
      on_compaction: false  # rotate after context compaction
      max_turns: 0          # 0 = unlimited; N = turns per segment
```

| Key | Default | Behavior |
|---|---:|---|
| `on_compaction` | `false` | Rotate after compaction completes, at the next turn boundary. |
| `max_turns` | `0` | Rotate after every N completed turns; `0` disables the cap. |

Both defaults preserve one session scope for the full session. Rotated spans retain the same `session_id` and add `hermes.session.segment` plus `hermes.session.segment_reason` (`compaction` or `max_turns`).

## Adding a bundled plugin

Bundled plugins are written exactly like any other Hermes plugin — see [Build a Hermes Plugin](../../developer-guide/plugins/index.md). The only differences are:

- Directory lives at `<repo>/plugins/<name>/` instead of `~/.hermes/plugins/<name>/`
- Manifest source is reported as `bundled` in `hermes plugins list`
- User plugins with the same name override the bundled version

A plugin is a good candidate for bundling when:

- It has no optional dependencies (or they are already in the declared `all` extra)
- The behaviour benefits most users and is opt-out rather than opt-in
- The logic ties into lifecycle hooks that the agent would otherwise have to remember to invoke
- It complements a core capability without expanding the model-visible tool surface

Counter-examples — things that should stay as user-installable plugins, not bundled: third-party integrations with API keys, niche workflows, large dependency trees, anything that would meaningfully change agent behaviour by default.
