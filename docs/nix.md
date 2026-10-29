# Nix

The flake pins the development toolchain and the T3 server's packages. Run
commands from the repository root.

```bash
nix develop                 # python3, node 24, gh, jq, ripgrep, nixfmt
nix flake check             # botfile gates and toolbox selfcheck
```

sandbox-host, the k3s sandbox pool node, is configured in yggdrasil
(gitlab percs/yggdrasil, `nixos/`).

## Shared server tooling

The `botfiles` package installs `botfile`, `toolbox` and `botfiles-provision`.
Run `botfiles-provision` as each login to register the toolbox.

[Back to the README](../README.md)
