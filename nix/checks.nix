# The same gates CI runs, as derivations, so `nix flake check` and the GitHub
# workflow cannot drift apart.
{ pkgs, src }:

let
  botfile =
    name:
    pkgs.runCommand "botfile-${name}"
      {
        nativeBuildInputs = [ pkgs.python3 ];
      }
      ''
        cp -r ${src} repo
        chmod -R u+w repo
        python3 repo/bin/botfile ${name}
        touch $out
      '';
in
{
  botfile-selfcheck = botfile "selfcheck";
  botfile-validate = botfile "validate";
  botfile-budget-check = botfile "budget-check";
}
