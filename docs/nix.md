# Nix

The flake pins the development toolchain and the remote sandbox host. Run
commands from the repository root.

```bash
nix develop                 # python3, node 24, gh, jq, sops
nix flake check             # botfile gates, toolbox selfcheck, shared skill verification
```

## sandbox-host

`nixosConfigurations.sandbox-host` configures the remote T3 Code server on the
TrueNAS guest. Claude Code and Codex run on this server under the human user;
the MacBook connects as a T3 client. Microsandbox is independently available
for explicit KVM workloads, and is not the T3 provider launcher.

```bash
nixos-rebuild switch --flake .#sandbox-host \
  --target-host sandbox-host.<tailnet>.ts.net
```

Disks are declarative (disko: OS, workspace, cache, artifacts on four VirtIO
disks), secrets are sops + age with only ciphertext committed, and the access
posture is deny-by-default: no LAN ports, `trustedInterfaces = [ "tailscale0" ]`,
no password auth anywhere, Tailscale SSH as the authentication boundary. When
tailscale itself is down the recovery path is the TrueNAS VNC console, on
purpose.

`msb doctor` runs at boot as `microsandbox-preflight.service`, so a hypervisor
with nested virtualization switched off fails there rather than at the first
agent job.

Both human logins get the T3 Code server CLI (`t3`) from the pinned
`llm-agents` input, with Claude Code and Codex on its provider PATH. Run
`t3 serve` as your user to start it. For `percules`, the `t3code` systemd user
service starts at boot and survives logout, serving on port 3773 through the
tailnet firewall. Manage it with `systemctl --user status t3code` or
`systemctl --user restart t3code`. The same package is available with
`nix run .#t3code -- serve`; update it with `nix flake update llm-agents` and
rebuild the host.

Known gaps, documented rather than hidden: microsandbox 0.7.x is a CLI with no
daemon or HTTP API, so there is no job-submission endpoint to wrap - agents
reach the host over Tailscale SSH and drive `msb` directly. The systemd slice
bounds module-managed units, not sandboxes started from an interactive session,
and there is no TTL reaper yet.

[Back to the README](../README.md)

## Shared server tooling

The `botfiles` package installs `botfile`, `toolbox` and `botfiles-provision`.
Home Manager wires Claude and Codex instructions from that package. Run
`botfiles-provision` as each login to register the toolbox. Bask skills are not
packaged: the `bask-skills` user timer keeps a pulled clone, see [shared skills](skills.md).
