# macOS Home Manager installation, managed configuration and optional launchd services.
# Desktop and administrative commands share the same profile home and Nix runtime.
{ inputs, ... }:
{
  flake.homeManagerModules.default =
    {
      config,
      lib,
      options,
      pkgs,
      ...
    }:

    let
      cfg = config.services.hermes-agent;
      cfgPrograms = config.programs.hermes-agent;
      common = import ./moduleCommon.nix { inherit lib; };

      effectivePackage = common.effectivePackage cfg;
      hermes-agent = inputs.self.packages.${pkgs.stdenv.hostPlatform.system}.default;

      inherit (pkgs.stdenv.hostPlatform) isDarwin;

      processEnvironment = common.processEnvironment {
        inherit (cfg) hermesHome;
        # The CLI reads this value and names it when it refuses a
        # configuration change.
        managedSystem = "home-manager";
      };
      unitPath = lib.makeBinPath (common.processPath { inherit pkgs cfg; });

      # ── The desktop launcher ───────────────────────────────────────────
      # A GUI launcher reads no shell profile, so home.sessionVariables does
      # not reach it, and the application would open ~/.hermes while the
      # services use hermesHome. Thus the launcher carries the value itself.
      #
      # HERMES_MANAGED rides along only when the services are enabled. That
      # variable makes the CLI refuse a configuration change and name the
      # rebuild command. A person who enables `programs.` alone has no
      # activation and no managed configuration, so the application must not
      # claim one and refuse an edit that nothing else owns.
      desktopEnvironment = {
        HERMES_HOME = cfg.hermesHome;
      }
      // lib.optionalAttrs cfg.enable {
        inherit (processEnvironment) HERMES_MANAGED;
      }
      // lib.optionalAttrs desktopUsesService {
        HERMES_DESKTOP_REMOTE_URL = "http://${cfg.backend.host}:${toString cfg.backend.port}";
      };

      # The application reaches the backend of the service only when there is
      # a backend to reach AND a shared token to present with. Without the
      # token the desktop resolver throws ("HERMES_DESKTOP_REMOTE_URL is set
      # but HERMES_DESKTOP_REMOTE_TOKEN is not"), so the two variables travel
      # together or not at all.
      desktopUsesService = cfg.enable && cfg.backend.mode != "none" && cfg.backend.sessionTokenFile != null;

      # The token is read at start time and never with `--set`. makeWrapper
      # writes a --set value into the Nix store, which all users can read.
      desktopRun = lib.optional desktopUsesService ''
        if [ -r ${lib.escapeShellArg cfg.backend.sessionTokenFile} ]; then
          HERMES_DESKTOP_REMOTE_TOKEN="$(tr -d '\r\n' < ${lib.escapeShellArg cfg.backend.sessionTokenFile})"
          export HERMES_DESKTOP_REMOTE_TOKEN
        else
          echo "hermes-desktop: cannot read the session token at ${cfg.backend.sessionTokenFile}." >&2
          echo "hermes-desktop: the application starts its own backend instead of the one of the service." >&2
        fi
      '';

      # `override`, and not `overrideAttrs`: the values go into the wrapper
      # that the installPhase writes, and not into a derivation attribute.
      desktopPackage = cfgPrograms.desktop.package.override {
        extraEnv = desktopEnvironment;
        extraRun = desktopRun;
      };

      mkAgent =
        { argv, logName }:
        {
          enable = true;
          config = {
            Label = "org.nix-community.home.${logName}";
            ProgramArguments = argv;
            EnvironmentVariables = processEnvironment // {
              PATH = "${unitPath}:/usr/bin:/bin:/usr/sbin:/sbin";
            };
            WorkingDirectory = cfg.workingDirectory;
            RunAtLoad = true;
            KeepAlive =
              if cfg.restart == "always" then
                true
              else
                {
                  SuccessfulExit = false;
                  Crashed = true;
                };
            ThrottleInterval = cfg.restartSec;
            StandardOutPath = "${config.home.homeDirectory}/Library/Logs/${logName}.log";
            StandardErrorPath = "${config.home.homeDirectory}/Library/Logs/${logName}.err.log";
            ProcessType = "Background";
          };
        };

    in
    {
      # ── programs.hermes-agent — the installation ───────────────────────
      # Home Manager separates "install this application for me" from "run
      # this daemon". Hermes needs both, and a person can want one without
      # the other: an application with no gateway, or a headless gateway on
      # a machine with no display.
      #
      # `services.hermes-agent` stays the authority for the state and the
      # configuration. This module reads hermesHome and the backend address
      # from it, and never the reverse.
      options.programs.hermes-agent = {
        enable = lib.mkEnableOption ''
          the Hermes Agent command line application.

          This adds `hermes` to home.packages, and exports HERMES_HOME with
          home.sessionVariables. An interactive shell then uses the same
          state as `services.hermes-agent`
        '';

        package = lib.mkOption {
          type = lib.types.package;
          default = effectivePackage;
          defaultText = lib.literalExpression "config.services.hermes-agent.package";
          description = ''
            The hermes-agent package to install.

            The default follows `services.hermes-agent.package`, and applies
            `extraPythonPackages` and `extraDependencyGroups` from that
            module. Thus the command line and the services are one build,
            and a plugin that the services can load is a plugin that your
            shell can load.
          '';
        };

        desktop = {
          enable = lib.mkEnableOption ''
            the Hermes Desktop application (Electron).

            This adds `hermes-desktop` to home.packages. The launcher starts the same Hermes
            runtime that `package` gives, and reads the HERMES_HOME of
            `services.hermes-agent`. Thus the application, the interactive
            shell and the services share one state directory.

            The Electron application carries its own Hermes runtime with
            the usual distribution. This module gives it the Nix package
            instead, with HERMES_DESKTOP_HERMES. It installs no second copy
            of Hermes, and it downloads nothing on the first start
          '';

          package = lib.mkOption {
            type = lib.types.package;
            default = cfgPrograms.package.hermesDesktop;
            defaultText = lib.literalExpression "config.programs.hermes-agent.package.hermesDesktop";
            description = ''
              The hermes-desktop package to use.

              The default follows `package`, and thus also
              `services.hermes-agent.extraPythonPackages` and
              `extraDependencyGroups`, because the desktop application is a
              passthru of the agent package. A package that you set here
              carries its own Hermes runtime, and this module cannot make
              it agree with the services.
            '';
          };
        };
      };

      options.services.hermes-agent =
        common.sharedOptions {
          defaultPackage = hermes-agent;
          defaultPackageText = lib.literalExpression "hermes-agent.packages.\${system}.default";
          defaultWorkingDirectory = config.home.homeDirectory;
          defaultWorkingDirectoryText = lib.literalExpression "config.home.homeDirectory";
        }
        // {
          hermesHome = lib.mkOption {
            type = lib.types.str;
            default = "${config.home.homeDirectory}/.hermes";
            defaultText = lib.literalExpression ''"''${config.home.homeDirectory}/.hermes"'';
            description = ''
              The value of HERMES_HOME. This state directory holds
              config.yaml, .env, auth.json, the sessions, the skills, the
              memory and the cron jobs.

              This module sets HERMES_HOME directly. Thus an existing
              ~/.hermes continues to work, and you can give the directory any
              name.
            '';
            example = "/Users/alice/.hermes-work";
          };

          # `installPackage` moved to `programs.hermes-agent.enable`. The
          # option is dead, but it must not be silent: it defaulted to true,
          # so a person who never named it still got the command line, and a
          # quiet removal gives them a machine with no `hermes` and no
          # message. mkOption with an assertion, and not
          # mkRemovedOptionModule, because the message must name the exact
          # replacement for the value they set.
          installPackage = lib.mkOption {
            type = lib.types.nullOr lib.types.bool;
            default = null;
            visible = false;
            description = ''
              Removed. Use `programs.hermes-agent.enable` instead.
            '';
          };

          gateway.enable = lib.mkEnableOption "the local Desktop Gateway runtime";
        };

      config = lib.mkMerge [

        # ── programs.hermes-agent — the installation ──────────────────────
        # Outside the `services.enable` guard on purpose. A person can want
        # the command line or the application on a machine that runs no
        # daemon at all.
        (lib.mkIf cfgPrograms.enable {
          home.packages = [ cfgPrograms.package ];
          home.sessionVariables.HERMES_HOME = cfg.hermesHome;
        })

        # GUI launchers carry their profile home explicitly; they do not read shell profiles.
        (lib.mkIf cfgPrograms.desktop.enable {
          home.packages = [ desktopPackage ];
        })

        {
          assertions = [
            {
              assertion = !(cfg.enable || cfgPrograms.enable || cfgPrograms.desktop.enable) || isDarwin;
              message = "Hermes Home Manager supports macOS only.";
            }
            {
              # `installPackage` was removed in favour of the programs/services
              # split. It defaulted to true, so a quiet removal leaves a person
              # with no `hermes` on the PATH and no message.
              assertion = cfg.installPackage == null;
              message = common.installPackageRemovedMessage cfg.installPackage;
            }
          ];
        }

        (lib.mkIf cfg.enable (
          lib.mkMerge [

            # ── Merge MCP servers into settings ────────────────────────────
            (lib.mkIf (cfg.mcpServers != { }) {
              services.hermes-agent.settings.mcp_servers = common.mcpServersToConfig cfg.mcpServers;
            })

            {
              assertions =
                common.pluginNameAssertions {
                  inherit cfg;
                  optionPath = "services.hermes-agent";
                }
                ++ common.workspaceFilesAssertions {
                  inherit cfg;
                  opt = options.services.hermes-agent.workingDirectory;
                  optionPath = "services.hermes-agent";
                };
            }

            # The agent runs these tools, so they belong on the PATH of the
            # person as well as in the unit.
            (lib.mkIf cfgPrograms.enable {
              home.packages = cfg.extraPackages;
            })

            # ── Activation: directories, config, secrets, documents ────────
            {
              # The activation runs after writeBoundary, when the home.file
              # symlinks are in place. It also runs after linkGeneration, when
              # Home Manager completes the switch. A secret that the activation
              # entry of sops-nix writes exists at that point.
              home.activation.hermesAgentSetup =
                lib.hm.dag.entryAfter
                  [
                    "writeBoundary"
                    "linkGeneration"
                  ]
                  (
                    common.mkStateScript {
                      inherit pkgs cfg;
                      inherit (cfg) hermesHome workingDirectory;
                      run = "$DRY_RUN_CMD ";
                      stateDirs = common.stateSubdirs;
                      managedSystem = "home-manager";
                      # This state has one user. No group needs access to it.
                      modes = {
                        config = "0600";
                        env = "0600";
                        managed = "0600";
                        auth = "0600";
                        document = "0600";
                      };
                    }
                  );
            }

            # ── Darwin: launchd agents ─────────────────────────────────────
            (lib.mkIf (isDarwin && cfg.gateway.enable) {
              launchd.agents.hermes-agent = mkAgent {
                argv = common.gatewayArgv cfg;
                logName = "hermes-agent";
              };
            })

            (lib.mkIf (isDarwin && cfg.backend.mode != "none") {
              launchd.agents.hermes-backend = mkAgent {
                argv = common.backendArgv { inherit pkgs cfg; };
                logName = "hermes-backend";
              };
            })
          ]
        ))
      ];
    };
}
