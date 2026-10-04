# The same gates CI runs, as derivations, so `nix flake check` and the GitHub
# workflow cannot drift apart.
{ pkgs, src }:

let
  gate =
    tool: name:
    pkgs.runCommand "${tool}-${name}"
      {
        nativeBuildInputs = [ pkgs.python3 ];
      }
      ''
        cp -r ${src} repo
        chmod -R u+w repo
        python3 repo/bin/${tool} ${name}
        touch $out
      '';
in
{
  botfile-selfcheck = gate "botfile" "selfcheck";
  botfile-validate = gate "botfile" "validate";
  botfile-budget-check = gate "botfile" "budget-check";
  toolbox-selfcheck = gate "toolbox" "selfcheck";
}
