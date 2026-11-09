# Native macOS package, runtime and Home Manager verification.
{ inputs, ... }: {
  perSystem = { pkgs, lib, self', ... }:
    let
      hermes-agent = self'.packages.default;
      hermesVenv = hermes-agent.hermesVenv;
      configMergeScript = pkgs.callPackage ./configMergeScript.nix { };
      pythonLock = pkgs.callPackage ./pythonLock.nix { };
      configKeys = pkgs.runCommand "hermes-config-keys" {} ''
        set -euo pipefail
        export HOME=$TMPDIR
        ${hermesVenv}/bin/python3 -c '
import json, sys
from hermes_cli.config import DEFAULT_CONFIG

def leaf_paths(d, prefix=""):
    paths = []
    for k, v in sorted(d.items()):
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict) and v:
            paths.extend(leaf_paths(v, path))
        else:
            paths.append(path)
    return paths

json.dump(sorted(leaf_paths(DEFAULT_CONFIG)), sys.stdout, indent=2)
' > $out
      '';
      evalHome = settings: inputs.home-manager.lib.homeManagerConfiguration {
        inherit pkgs;
        modules = [
          inputs.self.homeManagerModules.default
          {
            home = {
              username = "hermes-check";
              homeDirectory = "/Users/hermes-check";
              stateVersion = "24.11";
            };
          }
          settings
        ];
      };
    in {
      packages.configKeys = configKeys;
      checks = {
        pm-packages-unpack = pkgs.runCommand "hermes-pm-packages-unpack" { } ''
          test -x ${self'.packages.pm-iron-proxy}/iron-proxy
          mkdir -p $out
          echo "ok" > $out/result
        '';

        dev-venv-self-contained = pkgs.runCommand "hermes-dev-venv-self-contained" { } ''
          venv=${hermes-agent.devVenv}
          env -i "$venv/bin/python3" -c '
          import sys, ruamel.yaml, openai, httpx, pytest
          assert sys.prefix == "'"$venv"'", sys.prefix
          assert sys.base_prefix == "${hermes-agent.pmPython}", sys.base_prefix
          '
          env -i "$venv/bin/pytest" --version
          # Native dev commands survive alongside the re-shebanged scripts.
          env -i "$venv/bin/ruff" --version
          env -i "$venv/bin/ty" --version
          mkdir -p $out
          echo ok > $out/result
        '';

        build-package = pkgs.runCommand "hermes-build-package" { } ''
          echo "PASS: package built at ${hermes-agent}"
          mkdir -p $out
          echo "ok" > $out/result
        '';

        frontend-icons = pkgs.runCommand "hermes-frontend-icons" {
          nativeBuildInputs = [ (pkgs.python3.withPackages (ps: [ ps.pillow ])) ];
        } ''
          python3 - <<'PY'
          from pathlib import Path
          from PIL import Image

          desktop = Path('${self'.packages.desktop}/share')
          dist = desktop / 'hermes-desktop/dist'
          launcher = desktop / 'hermes-desktop/assets/icon.png'
          for path in [launcher, dist / 'apple-touch-icon.png']:
              with Image.open(path) as image:
                  image.load()
                  assert image.width > 0 and image.height > 0, path
          with Image.open(launcher) as image, Image.open(dist / 'apple-touch-icon.png') as window_icon:
              assert image.size == window_icon.size
              assert image.convert('RGBA').tobytes() == window_icon.convert('RGBA').tobytes()
          print('PASS: desktop ships decodable generated icons; launcher matches window icon')
          PY
          mkdir -p $out
        '';

        build-devshell = pkgs.runCommand "hermes-build-devshell" { } ''
          echo "PASS: devShell built at ${self'.devShells.default}"
          mkdir -p $out
          echo "ok" > $out/result
        '';

        entry-points-sync = pkgs.runCommand "hermes-entry-points-sync" { } ''
          ${hermes-agent.python}/bin/python3 ${./tests/agent-references.py} \
            ${hermes-agent} ${../pyproject.toml} ${hermes-agent.agentInputsFile}
          mkdir -p $out
        '';

        cli-commands = pkgs.runCommand "hermes-cli-commands" { } ''
          set -e
          export HOME=$(mktemp -d)

          echo "=== Checking hermes --help ==="
          ${hermes-agent}/bin/hermes --help 2>&1 | grep -q "gateway" || (echo "FAIL: gateway subcommand missing"; exit 1)
          ${hermes-agent}/bin/hermes --help 2>&1 | grep -q "config" || (echo "FAIL: config subcommand missing"; exit 1)
          echo "PASS: All subcommands accessible"

          echo "=== All CLI checks passed ==="
          mkdir -p $out
          echo "ok" > $out/result
        '';

        python-lock-derived = pkgs.runCommand "hermes-python-lock-derived" { } ''
          set -e
          echo "=== Checking Nix Python derives from pm/lock.json ==="
          family=${pythonLock.family}
          echo "locked family: $family"
          if [ "$family" != "$(${hermesVenv}/bin/python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" ]; then
            echo "FAIL: selected interpreter major.minor does not match pm/lock.json"; exit 1
          fi
          echo "PASS: interpreter matches lock"
          mkdir -p $out
          echo "ok" > $out/result
        '';

        python-lock-no-fallback = let
          inherit (pythonLock) selectPython;
          lockedFamily = pythonLock.family;
          # Fake package sets as data: matching family -> selected; absent
          # family -> throw (never silently pick another interpreter).
          matching = { "python${builtins.replaceStrings [ "." ] [ "" ] lockedFamily}" = "fake-python-matching"; };
          missing = { };
          selected = selectPython lockedFamily matching;
          threw = !(builtins.tryEval (selectPython lockedFamily missing)).success;
        in pkgs.runCommand "hermes-python-lock-no-fallback" { } ''
          set -e
          echo "=== Checking python selector has no silent fallback ==="
          if [ "${toString (selected == "fake-python-matching")}" != "1" ] || [ "${toString threw}" != "1" ]; then
            echo "FAIL: selector behavior wrong (selected=${toString selected} threw=${toString threw})"; exit 1
          fi
          echo "PASS: selector picks locked family, throws on missing family"
          mkdir -p $out
          echo "ok" > $out/result
        '';

        extra-dependency-groups = let
          hermesWithGroups = hermes-agent.override {
            extraDependencyGroups = [ "exa" ];
          };
        in pkgs.runCommand "hermes-extra-dependency-groups" { } ''
          set -e
          echo "=== Checking extraDependencyGroups override evaluates ==="

          # Eval-only: verify the override produces valid derivation paths
          # without building the full venv (which is expensive and redundant
          # since the mechanism is just list concatenation into python.nix).
          echo "derivation: ${hermesWithGroups}"
          echo "venv: ${hermesWithGroups.hermesVenv}"
          echo "PASS: extraDependencyGroups override evaluates cleanly"

          echo "=== All extraDependencyGroups checks passed ==="
          mkdir -p $out
          echo "ok" > $out/result
        '';

        generated-config-version =
          let
            common = import ./moduleCommon.nix { inherit lib; };
            configFiles = common.mkConfigFiles {
              inherit pkgs;
              cfg = {
                package = hermes-agent;
                extraPythonPackages = [ ];
                extraDependencyGroups = [ ];
                configFile = null;
                settings.model.default = "test/nix-model";
              };
              workingDirectory = "/Users/hermes-check/workspace";
            };
          in
          pkgs.runCommand "hermes-generated-config-version" { } ''
            set -e
            export HOME=$(mktemp -d) HERMES_HOME=$(mktemp -d)
            ${configMergeScript} ${configFiles.generated} "$HERMES_HOME/config.yaml"
            ${hermesVenv}/bin/python3 -c '
            from hermes_cli.config import check_config_version
            current, latest = check_config_version(raise_on_parse_error=True)
            assert current == latest, f"generated config.yaml reads as v{current}, package is v{latest}"
            print(f"PASS: generated config.yaml is at v{current}")
            '
            mkdir -p $out
            echo "ok" > $out/result
          '';

        config-roundtrip = let
          # Nix settings used across scenarios
          nixSettings = pkgs.writeText "nix-settings.json" (builtins.toJSON {
            model = "test/nix-model";
            toolsets = ["nix-toolset"];
            terminal = { backend = "docker"; timeout = 999; };
            mcp_servers = {
              nix-server = { command = "echo"; args = ["nix"]; };
            };
          });

          # Pre-built YAML fixtures for each scenario
          fixtureB = pkgs.writeText "fixture-b.yaml" ''
            model: "old-model"
            mcp_servers:
              old-server:
                url: "http://old"
          '';
          fixtureC = pkgs.writeText "fixture-c.yaml" ''
            skills:
              disabled:
                - skill-a
                - skill-b
            session_reset:
              mode: idle
              idle_minutes: 30
            streaming:
              enabled: true
            fallback_model:
              provider: openrouter
              model: test-fallback
          '';
          fixtureD = pkgs.writeText "fixture-d.yaml" ''
            model: "user-model"
            skills:
              disabled:
                - skill-x
            streaming:
              enabled: true
              transport: edit
          '';
          fixtureE = pkgs.writeText "fixture-e.yaml" ''
            mcp_servers:
              user-server:
                url: "http://user-mcp"
              nix-server:
                command: "old-cmd"
                args: ["old"]
          '';
          fixtureF = pkgs.writeText "fixture-f.yaml" ''
            terminal:
              cwd: "/user/path"
              custom_key: "preserved"
              env_passthrough:
                - USER_VAR
          '';

        in pkgs.runCommand "hermes-config-roundtrip" {
          nativeBuildInputs = [ pkgs.jq ];
        } ''
          set -e
          export HOME=$(mktemp -d)
          ERRORS=""

          fail() { ERRORS="$ERRORS\nFAIL: $1"; }

          # Helper: run merge then load with Python, output merged JSON
          merge_and_load() {
            local hermes_home="$1"
            export HERMES_HOME="$hermes_home"
            ${configMergeScript} ${nixSettings} "$hermes_home/config.yaml"
            ${hermesVenv}/bin/python3 -c '
import json, sys
from hermes_cli.config import load_config
json.dump(load_config(), sys.stdout, default=str)
'
          }

          # ═══════════════════════════════════════════════════════════════
          # Scenario A: Fresh install — no existing config.yaml
          # ═══════════════════════════════════════════════════════════════
          echo "=== Scenario A: Fresh install ==="
          A_HOME=$(mktemp -d)
          A_CONFIG=$(merge_and_load "$A_HOME")

          echo "$A_CONFIG" | jq -e '.model == "test/nix-model"' > /dev/null \
            || fail "A: model not set from Nix"
          echo "$A_CONFIG" | jq -e '.mcp_servers."nix-server".command == "echo"' > /dev/null \
            || fail "A: MCP nix-server missing"
          echo "PASS: Scenario A"

          # ═══════════════════════════════════════════════════════════════
          # Scenario B: Nix keys override existing values
          # ═══════════════════════════════════════════════════════════════
          echo "=== Scenario B: Nix overrides ==="
          B_HOME=$(mktemp -d)
          install -m 0644 ${fixtureB} "$B_HOME/config.yaml"
          B_CONFIG=$(merge_and_load "$B_HOME")

          echo "$B_CONFIG" | jq -e '.model == "test/nix-model"' > /dev/null \
            || fail "B: Nix model did not override"
          echo "PASS: Scenario B"

          # ═══════════════════════════════════════════════════════════════
          # Scenario C: User-only keys preserved
          # ═══════════════════════════════════════════════════════════════
          echo "=== Scenario C: User keys preserved ==="
          C_HOME=$(mktemp -d)
          install -m 0644 ${fixtureC} "$C_HOME/config.yaml"
          C_CONFIG=$(merge_and_load "$C_HOME")

          echo "$C_CONFIG" | jq -e '.skills.disabled == ["skill-a", "skill-b"]' > /dev/null \
            || fail "C: skills.disabled not preserved"
          echo "$C_CONFIG" | jq -e '.session_reset.mode == "idle"' > /dev/null \
            || fail "C: session_reset.mode not preserved"
          echo "$C_CONFIG" | jq -e '.session_reset.idle_minutes == 30' > /dev/null \
            || fail "C: session_reset.idle_minutes not preserved"
          echo "$C_CONFIG" | jq -e '.streaming.enabled == true' > /dev/null \
            || fail "C: streaming.enabled not preserved"
          echo "$C_CONFIG" | jq -e '.fallback_model.provider == "openrouter"' > /dev/null \
            || fail "C: fallback_model not preserved"
          echo "PASS: Scenario C"

          # ═══════════════════════════════════════════════════════════════
          # Scenario D: Mixed — Nix wins for its keys, user keys preserved
          # ═══════════════════════════════════════════════════════════════
          echo "=== Scenario D: Mixed merge ==="
          D_HOME=$(mktemp -d)
          install -m 0644 ${fixtureD} "$D_HOME/config.yaml"
          D_CONFIG=$(merge_and_load "$D_HOME")

          echo "$D_CONFIG" | jq -e '.model == "test/nix-model"' > /dev/null \
            || fail "D: Nix model did not override user model"
          echo "$D_CONFIG" | jq -e '.skills.disabled == ["skill-x"]' > /dev/null \
            || fail "D: user skills not preserved"
          echo "$D_CONFIG" | jq -e '.streaming.enabled == true' > /dev/null \
            || fail "D: user streaming not preserved"
          echo "PASS: Scenario D"

          # ═══════════════════════════════════════════════════════════════
          # Scenario E: MCP additive merge
          # ═══════════════════════════════════════════════════════════════
          echo "=== Scenario E: MCP additive merge ==="
          E_HOME=$(mktemp -d)
          install -m 0644 ${fixtureE} "$E_HOME/config.yaml"
          E_CONFIG=$(merge_and_load "$E_HOME")

          echo "$E_CONFIG" | jq -e '.mcp_servers."user-server".url == "http://user-mcp"' > /dev/null \
            || fail "E: user MCP server not preserved"
          echo "$E_CONFIG" | jq -e '.mcp_servers."nix-server".command == "echo"' > /dev/null \
            || fail "E: Nix MCP server did not override same-name user server"
          echo "$E_CONFIG" | jq -e '.mcp_servers."nix-server".args == ["nix"]' > /dev/null \
            || fail "E: Nix MCP server args wrong"
          echo "PASS: Scenario E"

          # ═══════════════════════════════════════════════════════════════
          # Scenario F: Nested deep merge
          # ═══════════════════════════════════════════════════════════════
          echo "=== Scenario F: Nested deep merge ==="
          F_HOME=$(mktemp -d)
          install -m 0644 ${fixtureF} "$F_HOME/config.yaml"
          F_CONFIG=$(merge_and_load "$F_HOME")

          echo "$F_CONFIG" | jq -e '.terminal.backend == "docker"' > /dev/null \
            || fail "F: Nix terminal.backend did not override"
          echo "$F_CONFIG" | jq -e '.terminal.timeout == 999' > /dev/null \
            || fail "F: Nix terminal.timeout did not override"
          echo "$F_CONFIG" | jq -e '.terminal.custom_key == "preserved"' > /dev/null \
            || fail "F: terminal.custom_key not preserved"
          echo "$F_CONFIG" | jq -e '.terminal.cwd == "/user/path"' > /dev/null \
            || fail "F: user terminal.cwd not preserved when Nix does not set it"
          echo "$F_CONFIG" | jq -e '.terminal.env_passthrough == ["USER_VAR"]' > /dev/null \
            || fail "F: user terminal.env_passthrough not preserved"
          echo "PASS: Scenario F"

          # ═══════════════════════════════════════════════════════════════
          # Scenario G: Idempotency — merging twice yields the same result
          # ═══════════════════════════════════════════════════════════════
          echo "=== Scenario G: Idempotency ==="
          G_HOME=$(mktemp -d)
          install -m 0644 ${fixtureD} "$G_HOME/config.yaml"
          ${configMergeScript} ${nixSettings} "$G_HOME/config.yaml"
          FIRST=$(cat "$G_HOME/config.yaml")
          ${configMergeScript} ${nixSettings} "$G_HOME/config.yaml"
          SECOND=$(cat "$G_HOME/config.yaml")

          if [ "$FIRST" != "$SECOND" ]; then
            fail "G: second merge produced different output"
            echo "--- first ---"
            echo "$FIRST"
            echo "--- second ---"
            echo "$SECOND"
          fi
          echo "PASS: Scenario G"

          # ═══════════════════════════════════════════════════════════════
          # Report
          # ═══════════════════════════════════════════════════════════════
          if [ -n "$ERRORS" ]; then
            echo ""
            echo "FAILURES:"
            echo -e "$ERRORS"
            exit 1
          fi

          echo ""
          echo "=== All 7 merge scenarios passed ==="
          mkdir -p $out
          echo "ok" > $out/result
        '';

        home-manager-launchd = let
          enabled = (evalHome {
            programs.hermes-agent.enable = true;
            programs.hermes-agent.desktop.enable = true;
            services.hermes-agent = {
              enable = true;
              gateway.enable = true;
              hermesHome = "/Users/hermes-check/runtime";
              settings.model.default = "test/model";
            };
          }).config;
          standalone = (evalHome {
            programs.hermes-agent.desktop.enable = true;
          }).config;
          runtime = enabled.launchd.agents.hermes-agent.config;
          failures = lib.optional
            (runtime.ProgramArguments != [ "${enabled.services.hermes-agent.package}/bin/hermes" "gateway" ])
            "launchd must start the local Gateway"
            ++ lib.optional (runtime.EnvironmentVariables.HERMES_HOME != "/Users/hermes-check/runtime")
              "launchd must bind the configured profile home"
            ++ lib.optional (builtins.hasAttr "hermes-agent" standalone.launchd.agents)
              "installing Desktop alone must not create a background service"
            ++ lib.optional (builtins.hasAttr "hermesAgentSetup" standalone.home.activation)
              "standalone Desktop must not take ownership of user configuration"
            ++ lib.optional (!lib.all (item: item.assertion) enabled.assertions)
              "enabled Home Manager configuration must satisfy its assertions";
        in pkgs.runCommand "hermes-home-manager-launchd" { } (
          if failures != [ ] then throw (lib.concatStringsSep "\n" failures)
          else ''
            test -x ${self'.packages.desktop}/bin/hermes-desktop
            mkdir -p $out
          ''
        );

        desktop-runtime-scope = pkgs.runCommand "hermes-desktop-runtime-scope" { } ''
          export HERMES_HOME="$TMPDIR/profile"
          mkdir -p "$HERMES_HOME"
          ${hermesVenv}/bin/python3 - <<'PY'
          import os
          from pathlib import Path
          from gateway.config import load_gateway_config

          home = Path(os.environ["HERMES_HOME"])
          home.joinpath("config.yaml").write_text(
              "platforms:\n  telegram:\n    enabled: true\n    token: retired-token\n"
              "  webhook:\n    enabled: true\n")
          os.environ["TELEGRAM_BOT_TOKEN"] = "retired-token"
          os.environ["WEBHOOK_ENABLED"] = "true"
          assert load_gateway_config().platforms == {}
          PY
          mkdir -p $out
        '';
      };
    };
}
