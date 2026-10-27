# secrets

Encrypted with [sops](https://github.com/getsops/sops) + age; only the
ciphertext is committed. `hosts/sandbox-host/default.nix` wires sops-nix **only
if `sandbox-host.yaml` exists**, so a fresh checkout evaluates without it and
the host simply expects a manual `tailscale up` and has no k3s token.

Decryption on the host uses its SSH host key, converted to an age key by
sops-nix. So the host must exist before its secrets can be encrypted to it.

## First time

```bash
nix develop                                    # sops + age + ssh-to-age
ssh admin@sandbox-pool-1 'cat /etc/ssh/ssh_host_ed25519_key.pub' | ssh-to-age
```

Put the resulting `age1...` recipient in `.sops.yaml`, next to the operator's
own age key (so the file stays editable off the host), then create the file:

```bash
sops secrets/sandbox-host.yaml
```

with this shape:

```yaml
tailscale-authkey: tskey-auth-...
k3s-token: K10...
```

Every key the host declares must be present, or activation fails.

- `tailscale-authkey`: a **tag-owning, reusable** auth key, so the node can
  claim `tag:sandbox-pool` without an operator's personal identity.
- `k3s-token`: a bootstrap token from `sudo k3s token create --ttl 0
  --description sandbox-pool` on a yggdrasil server. It joins agents only;
  never use the server token.

Commit the resulting ciphertext, then `nixos-rebuild switch --flake .#sandbox-host`.

## Rotating

`sops secrets/sandbox-host.yaml` edits in place. Adding a recipient to
`.sops.yaml` needs `sops updatekeys secrets/sandbox-host.yaml` afterwards.
