# Building the macOS Desktop Installers

This operations build supports macOS (Apple Silicon and Intel) and Simplified Chinese only.

Use the complete bundle builder for release artifacts. Ordinary `dist:*`
commands package the current desktop build; they do not stage a fresh runtime.

## Artifact and update ownership

| Target | Artifact | Update owner |
|---|---|---|
| macOS ARM64 / x64 | Signed, notarized `Hermes.app` in DMG and ZIP artifacts | `electron-updater` with Squirrel.Mac |

`bundled` carries the local runtime. `light` is a remote client without Python
or a local agent. Only macOS Desktop packages are built.

## Payload contents

The bundled payload contains:

- The release's source snapshot without `.git`.
- Pinned CPython and uv, plus a ready Python dependency tree.
- Node.js, npm, supported managed tools, and prebuilt TUI/dashboard assets.
- A manifest, tool facts, the installed feature list, and build provenance.
- Generated CLI launchers from the archived project's script declarations.

`pm/lock.json` owns managed-tool pins. `pyproject.toml` and `uv.lock` own Python
requirements. Native staging uses `--all-extras`, subject to platform markers,
minus the extras `[tool.hermes] opt-in-extras` names (installed only when the
user selects them). This is broader than the source installer's extra named `all`.

The backend runs from app resources. Launchers execute the store interpreter
with the source and dependency paths; they do not boot through a relocated
venv executable. Startup can create user-state records and CLI links.
Provider calls, model downloads, and optional integration setup can still use
the network.

macOS uses system Git. A Mac without Command Line Tools can therefore
need them for Git-dependent operations.

User data remains outside the package. Optional additions use writable PM
storage and complete Python environment generations, not writes into the app.
See [Package management](../../website/docs/reference/package-management.md).

## Python runtime contract

The PM bundle builder records interpreter and dependency paths in the payload
manifest. `scripts/write-build-stamp.mjs` copies that runtime contract into the
desktop stamp. The desktop build embeds the stamp in Electron.
`electron/payload-backend.ts` reads `runtime.sitePackages` from this stamp.
It does not select a Python version or search for dependency directories.

Staging does not prove native startup or package replacement. Those checks
use the [bundled-update acceptance suite](../../tests/install/BUNDLED_UPDATES.md).
Acceptance requires a native run with the actual signed release artifacts.

Packaged tool facts describe the final bytes, not only the staged archives.
The macOS custom signer retains the builder's entitlements and file selection.
It refreshes digests after child signatures and before the outer app signature.
Unsigned macOS builds refresh them at the end of `afterPack`.
Do not refresh facts in `afterSign`: that changes resources covered by the signature.

## Local test build

To build the commit you have checked out, without a tag and without pushing:

```sh
scripts/build-bundle.sh            # macOS DMG/ZIP
```

The checkout must be clean, because the build packages `HEAD`. The script passes
`--clean` to the driver. The driver removes the previous outputs only after it holds
the checkout lock, so a second run cannot delete a build that is still going. Output
goes to `apps/desktop/release/`.

The scripts remove signing environment variables for local builds. macOS can still
sign nested binaries when it finds a Developer ID in your keychain.

## Complete native build

From a clean checkout whose `HEAD` equals the release tag, run:

```sh
python scripts/bundles/desktop.py --tag=vX.Y.Z
```

Replace `vX.Y.Z` with an actual immutable tag. Stable tags must match the
version in `pyproject.toml`. Canary tags use the release script's tag grammar.
Start with host Python 3.11+ and Git. Use `python3` if that is your host's command.
Preparation asks PM for the pinned Python, Node, npm and private installer;
preinstalling a separate Node/npm/uv toolchain is not required. Native dependency
builds still need the platform's compiler, SDK and libraries. macOS requires its native
developer tools. This is not a hermetic host SDK.

The builder:

1. Admits the clean source revision and prepares managed tools in isolated build state.
2. Prepares the locked JS workspace union, icon environment, Electron-native bindings,
   packaging utilities, and the application/independent PM environments when selected.
3. Compiles icons and the selected TUI, dashboard and desktop products.
4. Assembles the PM payload, places JS assets, relocates links, and generates launchers.
5. Consumes the prepared Electron archive and utilities to package the current OS.

Use `--variant light` for the remote client.
Arguments after `--` go to the prepared wrapper, which rejects overrides of
the admitted target, tools, output and configuration. `electron-builder.config.cjs`
is the sole packaging configuration. The wrapper disables automatic publishing;
the release workflow owns uploads and channel promotion.

`pm bundle --out DIR --ref REF` stages the native runtime only.
`scripts/bundles/stage.py` also builds the TUI/dashboard unless both products
are supplied explicitly. Both generate launchers; neither creates an Electron installer.
The launcher stage checks the payload and records its relative launch paths.
The Electron build bakes these paths into its stamp. Desktop startup does not
inspect, create, or repair a PM payload. Non-bundled builds carry no placeholder payload.
See [shared bundle builds](../../docs/shared-bundle-builds.md) for Termux reuse.

### Prepare once, then build

CI and local builds share the same split interface:

```sh
python scripts/bundles/desktop.py --tag vX.Y.Z --variant bundled --prepare-only \
  --work "$PWD/.build/desktop-job" --cache "$PWD/.cache/desktop-inputs"
python scripts/bundles/desktop.py --prepared "$PWD/.build/desktop-job/prepared.json"
```

The displayed paths are the defaults. Use separate build-owned work/cache roots;
do not pre-create the work directory. `prepared.json` is published after every
provider succeeds and contains absolute paths for this job, not a portable cache.
After relocation or a source/lock/tool change, prepare again. Consumption rejects
missing or changed dependencies without repairing or downloading them.

Release jobs restore candidates, prepare, save reusable inputs, and only then
build/sign. Job-local environments, credentials, products and signature results
are not dependency snapshot inputs. The signature cache retains its own lifetime.
Commit jobs request token-enforced read-only cache access; the conditional YAML
mode still needs GitHub acceptance (see the
[cache-policy caveat](../../docs/shared-bundle-builds.md#cache-ownership)). A
separate key or skipped save alone would not protect release caches. Archival remains an independent
prerequisite, and R2 upload credentials are not exposed to desktop preparation.

Strict consumption means no dependency acquisition, not offline signing.
Timestamp services, Azure signing, Apple notarization and publication remain
online operations. Validate unsigned packaging with dependency networking denied
on each target, then verify signed installers and launchers on their native hosts.

macOS packaging retains the caller's login `HOME` for keychain import and signing.
An explicit keychain path does not make Security.framework work under a scratch
home. Dependency preparation and product compilation still use the isolated home.
Hermes state and explicit dependency-cache paths remain build-owned during packaging.

## Commit-only builds

To preview a build for a pushed revision, run:

```sh
python scripts/release.py --build-commit REV --remote origin
```

The command fetches the remote and resolves `REV` to a full commit SHA.
It prints the dispatch command without changing local branches, tags, or releases.
Add `--publish` to dispatch that build. This flag does not publish a release
in commit-build mode.

Use repeatable `--bundle-env NAME=VALUE` options to bake non-secret runtime
defaults into the desktop app, for example:

```sh
python scripts/release.py --build-commit REV --remote fork --publish \
  --bundle-env HERMES_PREVIEW_FULL_CONNECTORS=1 \
  --bundle-env HERMES_DATA_DIR_SUFFIX=magic-test \
  --bundle-unset HERMES_HOME
```

These defaults run before Electron initializes its paths and are inherited by
local backend processes. Explicit runtime environment values win, including
empty values. Do not pass secrets: the values are visible in the workflow inputs
and packaged JavaScript. This option affects desktop bundles, not Termux.
The suffix is appended literally; include a leading hyphen if desired.
`--bundle-unset NAME` explicitly clears an inherited value at app launch, even
if the caller supplied it. Internally it sets the value to an empty string, not
an absent key.
For full data-path isolation, also clear `HERMES_DESKTOP_USER_DATA_DIR` if that
machine uses an explicit Electron directory. Ordinary defaults still preserve
runtime overrides; `--bundle-env HERMES_HOME=` is a default, not a forced clear.

For local commit builds, `HERMES_BUNDLE_ENV_JSON` accepts a JSON object whose
string values are defaults and whose `null` values are explicit clears. For example,
`{"HERMES_HOME":null,"HERMES_DATA_DIR_SUFFIX":"magic-test"}`. Only
`HERMES_HOME`, `HERMES_DATA_DIR_SUFFIX`, `HERMES_DESKTOP_USER_DATA_DIR`,
`HERMES_SHARED_AUTH_DIR`, and `HERMES_PREVIEW_FULL_CONNECTORS` are accepted. Process-control variables such as `NODE_OPTIONS` and `PATH`
are rejected. These settings are not applied to the build runner itself.
Commit archive keys still use the SHA, so use a fresh commit for different
defaults: an existing artifact is never overwritten with different bytes.

The workflow must exist on the repository's default branch. Admission requires
a default-branch `workflow_dispatch` and repository write, maintain, or admin
permission for both the original actor and the actor who reruns it.
It rejects mixed tag, release-phase, channel-publication, and upgrade inputs.

Builder jobs check out the admitted SHA. Their artifacts and completion receipts
go to `releases/commit/FULL_SHA/`, separate from tag archives and update channels.
The run summary lists macOS DMG/ZIP
files, and the Termux package. Linux release legs remain disabled and are listed
as not built. Only receipt-listed artifacts that exist in storage get download
links. Missing receipts show the failed or incomplete leg.

Each commit build also writes a downloads page to
`releases/commit/<FULL_SHA>/index.html` on the R2 public origin; a tag run
writes its channel page instead (`releases/stable/index.html` or
`releases/canary/index.html`). Pages list only objects the build actually
staged, and a re-run of an older tag never replaces a newer channel page.
`release.py --build-commit` prints the commit page URL before dispatching.

Commit builds require the signing credentials used by their release legs.
They do not produce Store packages or submit to Partner Center. No GitHub
release, updater feed, or APT channel is changed.
An identical upload retry can succeed. Different bytes at an existing commit
object key fail rather than replace that object.

For a local native build, check out the exact SHA and run:

```sh
python scripts/bundles/desktop.py --commit=FULL_SHA --variant=bundled
```

The builder uses that commit's project version.
Commit-built stamps disable automatic release-channel updates. Local command and transport tests do not
replace signed-package installation and update acceptance on each native host.

## macOS signing and updates

`CSC_LINK` and `CSC_KEY_PASSWORD` supply the Developer ID identity.
The notarization hook accepts `APPLE_API_KEY`, `APPLE_API_KEY_ID`, and
`APPLE_API_ISSUER`, or a keychain profile. CI materializes the API key from
`APPLE_API_KEY_P8`.

The app and nested Mach-O binaries, including Chromium, must be signed before
notarization. The existing after-sign hook owns submission and stapling.
Publication checks signatures, the stapled ticket, and Gatekeeper assessment.
Unsigned local builds do not satisfy these gates.

Both DMG and ZIP artifacts are required by the release pipeline. The ZIP is
the update artifact, not an optional duplicate of the download DMG.
See [macOS bundle updates](../../docs/macos-bundle-updates.md) for feed validation
and native-event ordering.

### DMG detach diagnostics

The builder wrapper reports `[dmg-detach]` snapshots when dmgbuild cannot detach
its staging image. It runs `lsof` before the supplier retries or performs forced
cleanup. The snapshot identifies the mounted filesystem, backing image and
devices, then lists process names, PIDs, parent PIDs, users, descriptors and paths.

The queries use noninteractive `sudo` when available. Permission failures and
query timeouts are reported explicitly. Empty output does not prove that the
image has no holder. The shim does not stop processes or change detach results,
retry settings, signing or notarization. Explicit `CUSTOM_DMGBUILD_PATH`
overrides outside the prepared path are not an escape hatch for strict builds.
Prepared packaging supplies the admitted dmgbuild path to the diagnostics shim.
Changes to its preparation provider need native DMG/detach and
signing/notarization acceptance; a successful download is not native execution proof.

## Development, assets, and verification

Prepare and activate the [PM developer environment](../../website/docs/reference/package-management.md#developer-workflow)
first. Use `source ./activate`, and keep a
separate development home. Activation supplies the toolchain, not `node_modules`.

From the repository root:

```sh
npm ci
npm run dev --workspace apps/desktop
```

For an ordinary package of that desktop build, use the workspace's
`dist:mac` or `pack` command. Those commands do not
replace the complete tagged build described above.

Icons are generated from `assets/nous-girl-*.svg` and `assets/backgrounds/`.
`node scripts/generate-icons.mjs` renders them with the Hermes runtime Python
(`HERMES_PYTHON`, else `python` on PATH); Pillow and resvg-py are core
dependencies. Generated PNG/ICO/ICNS files are not source assets.

[Stable release admission](../../docs/stable-releases.md) requires the full
pipeline, not just successful packaging. Native signed-package update tests
live in the [existing install/update family](../../tests/install/BUNDLED_UPDATES.md).
A helper test or unpacked-app smoke is not proof of native install, update,
or automatic relaunch. Historical receipts and current unresolved gates are
separate in [PM audit status](../../docs/pm-audit-status.md).
