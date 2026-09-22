# secrets

Encrypted with [sops](https://github.com/getsops/sops) + age; only the
ciphertext is committed. `hosts/sandbox-host/default.nix` wires sops-nix **only
if `sandbox-host.yaml` exists**, so a fresh checkout evaluates without it and
the host simply expects a manual `tailscale up`.

Decryption on the host uses its SSH host key, converted to an age key by
sops-nix. So the host must exist before its secrets can be encrypted to it.

## First time

```bash
nix develop                                    # sops + age + ssh-to-age
ssh sandbox-host 'cat /etc/ssh/ssh_host_ed25519_key.pub' | ssh-to-age
```

Put the resulting `age1...` recipient in `.sops.yaml`, replacing the
placeholder, then create the file:

```bash
sops secrets/sandbox-host.yaml
```

with this shape:

```yaml
tailscale-authkey: tskey-auth-...
```

Use a **tag-owning, reusable** auth key so the node can claim
`tag:sandbox-host` without an operator's personal identity. Commit the
resulting ciphertext, then `nixos-rebuild switch --flake .#sandbox-host`.

## Rotating

`sops secrets/sandbox-host.yaml` edits in place. Adding a recipient to
`.sops.yaml` needs `sops updatekeys secrets/sandbox-host.yaml` afterwards.
