{
  lib,
  stdenv,
  fetchurl,
  unzip,
}:
# The thin translation layer: pm/lock.json -> one fetched, unpacked
# derivation per package for this nix system. Nothing here knows versions,
# urls, or hashes — the lockfile is the complete machine interface, the
# same one `pm install` and `pm bundle` consume.
#
# Consumers pick what they need:   (callPackage ./pm-packages.nix { }).ripgrep
# Packages with no artifact for this system are simply absent.
let
  lock = builtins.fromJSON (builtins.readFile ../pm/lock.json);
  mirror = builtins.fromJSON (builtins.readFile ../pm/artifact-mirror.json);

  target = "darwin-${if stdenv.hostPlatform.isAarch64 then "arm64" else "x64"}";

  # A target pins one artifact or a list of them (a runtime split across
  # archives that must land in one directory). Normalize to a list.
  artifactsFor =
    pin:
    let
      found = pin.artifacts.${target} or pin.artifacts.any or null;
    in
    if found == null then null else if builtins.isList found then found else [ found ];

  # The archive suffixes pm/store.py::extract unpacks. A pin may also list
  # provenance sidecars (checksums.txt, .sig/.pem/.asc) that pm verifies at
  # install time; the fixed-output hash already pins the archive here, and
  # stdenv's unpackPhase has no unpacker for them, so they are left out.
  isArchive = artifact:
    lib.any (suffix: lib.hasSuffix suffix artifact.url) [ ".tar.gz" ".tgz" ".tar.xz" ".txz" ".tar.bz2" ".zip" ];

  derive = name: pin: artifacts:
    stdenv.mkDerivation {
      pname = name;
      version = pin.version;

      srcs = map (artifact: fetchurl {
        urls = [ artifact.url "${mirror.origin}/${mirror.prefix}${artifact.sha256}" ];
        sha256 = artifact.sha256;
      }) (builtins.filter isArchive artifacts);

      # pm's store publishes the unpacked tree; mirror that shape. Several
      # archives unpack over one another into the same root, exactly as
      # pm merges them into one store entry.
      sourceRoot = ".";
      nativeBuildInputs = lib.optional (lib.any (a: lib.hasSuffix ".zip" a.url) artifacts) unzip;
      dontBuild = true;
      dontConfigure = true;

      installPhase = ''
        mkdir -p $out
        cp -r . $out/
        # Nix's build-environment dump, not artifact content.
        rm -f $out/env-vars

        # Archives wrap their tree in one versioned directory
        # (`uv-aarch64-apple-darwin/`, `node-v26.12.1-darwin-arm64/`, `package/`).
        # pm's store strips it; mirror that so `$out/bin` is the entry point
        # instead of `$out/<archive-name>/bin`.
        shopt -s dotglob nullglob
        wrapped=() stray=()
        for entry in "$out"/*; do
          if [ -d "$entry" ]; then wrapped+=("$entry"); else stray+=("$entry"); fi
        done
        if [ ''${#wrapped[@]} -eq 1 ] && [ ''${#stray[@]} -eq 0 ]; then
          mv "''${wrapped[0]}"/* "$out"/
          rmdir "''${wrapped[0]}"
        fi
        shopt -u dotglob nullglob

        # Entry points also disagree: node and ffmpeg carry `bin/`, uv and
        # ripgrep put their executables at the root. PATH composition
        # (mkShell, lib.makeBinPath) only reads `bin`, so link root-level
        # executables into it.
        mkdir -p $out/bin
        for exe in "$out"/*; do
          [ -f "$exe" ] && [ -x "$exe" ] || continue
          ln -sf "../$(basename "$exe")" "$out/bin/$(basename "$exe")"
        done
      '';
    };
in
lib.filterAttrs (_: v: v != null) (
  lib.mapAttrs (
    name: pin:
    let
      artifacts = artifactsFor pin;
    in
    if artifacts == null then null else derive name pin artifacts
  ) lock.packages
)
