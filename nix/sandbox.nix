# The developer sandbox uses the host macOS isolation implementation.
{ writeShellApplication }:
writeShellApplication {
  name = "sandbox";
  text = ''
    exec ${../scripts/dev-sandbox.sh} "$@"
  '';
}
