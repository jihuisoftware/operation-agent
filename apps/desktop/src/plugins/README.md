# Bundled plugins

Drop a `<name>/plugin.{ts,tsx}` here that default-exports a `HermesPlugin` and
it registers automatically at boot (vite glob in `../contrib/plugins.ts`), with
the same inventory + live enable/disable contract as runtime plugins.

Keep this tree for real shipped plugins (and the small authoring fixtures that
dogfood the SDK). One-off demos that rebuild a core chrome piece 1:1 do not
belong here — they double the UI and confuse Capabilities ▸ Plugins. Publish those
in the companion
[`hermes-example-plugins`](https://github.com/NousResearch/hermes-example-plugins)
repo instead.

User- and agent-authored plugins load at runtime from
`$HERMES_HOME/desktop-plugins/<name>/plugin.js` (the disk door) — see the
`hermes-desktop-plugins` skill.

## Scheduler contributions

The SDK exports `CRON_BLUEPRINTS_AREA` (`cron.blueprints`) and
`CronBlueprintContribution`. Register a contribution with `data.render({ owner, view })`:
`view` is `summary` for the task page or `blueprints` for the template library.
`owner` contains the explicit connection ID and writable Profile. Pin every
`ctx.rest` request to that owner, and reset editor state when it changes. A template
click must not execute actions; authorization belongs to the plugin's apply flow.
The scheduler renders contributions without importing domain code. The bundled
operations plugin uses this seam for its versioned plan and private plugin API.
