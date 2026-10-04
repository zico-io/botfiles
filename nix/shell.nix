# Pinned tooling for the T3 server and this repository.
{ pkgs }:

pkgs.mkShell {
  packages = with pkgs; [
    python3 # memory CLI and skill synchronization
    nodejs_24 # T3 providers and shared Bask tooling
    gh
    jq
    ripgrep
    nixfmt
    sops
    age
    ssh-to-age # secrets/ workflow
  ];

  shellHook = ''
    echo "botfiles dev shell. Gates: bin/botfile validate | budget-check | selfcheck"
  '';
}
