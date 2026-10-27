# Nix

The flake pins the development toolchain and the remote sandbox host. Run
commands from the repository root.

```bash
nix develop                 # python3, node 24, gh, jq, sops
nix flake check             # botfile gates, toolbox selfcheck, shared skill verification
```

## sandbox-host

`nixosConfigurations.sandbox-host` configures the TrueNAS guest as a sandbox
pool node: a k3s agent of the home cluster yggdrasil, labeled and tainted
`pool=sandbox`. Each sandbox runs as a Kata VM through the `kata` containerd
runtime. The host has no logins of its own. Users run `ssh sandbox`, and the
gateway in yggdrasil picks their sandbox from the pool.

```bash
nixos-rebuild switch --flake .#sandbox-host \
  --target-host admin@sandbox-pool-1
```

Disks are declarative (disko: OS, sandbox homes at `/var/lib/sandboxes`, cache,
artifacts). Secrets are sops + age, with only ciphertext committed: the tailnet
auth key and the k3s bootstrap token. The firewall trusts `tailscale0` and the
pod interfaces, and admits kubelet and flannel from the three k3s servers only.
`sandbox-pool-1` on the tailnet is break-glass access for `admin`. When
tailscale itself is down, recover through the TrueNAS VNC console.

[Back to the README](../README.md)

## Shared server tooling

The `botfiles` package installs `botfile`, `toolbox` and `botfiles-provision`.
Run `botfiles-provision` as each login to register the toolbox.
