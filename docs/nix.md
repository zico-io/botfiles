# Nix

The flake pins the development toolchain and the CI gates. Run
commands from the repository root.

```bash
nix develop                 # python3, node 24, gh, jq, ripgrep, nixfmt
nix flake check             # botfile gates and toolbox selfcheck
```

sandbox-host, the k3s sandbox pool node, is configured in yggdrasil
(gitlab percs/yggdrasil, `nixos/`).

[Back to the README](../README.md)
