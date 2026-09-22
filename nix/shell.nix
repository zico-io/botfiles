# Reproducible toolchain for working on this repo. The sandbox image
# (sandbox/Containerfile) pins the same major versions on purpose: an agent
# inside a mission VM and a human in this shell should not see different tools.
{ pkgs }:

pkgs.mkShell {
  packages = with pkgs; [
    python3 # bin/botfile, orchestration/spawn.py
    nodejs_24 # eve requires >=24; pi's undici needs >=22
    cargo
    rustc
    clippy
    rustfmt # orbal-net
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
