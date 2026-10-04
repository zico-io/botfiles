# Sandbox

The local sandbox backend requires macOS on Apple Silicon and Apple's
`container` CLI. Run the commands below from the repository root. Fleet
placement uses herdr; see the [smoke test](../orchestration/smoke-test.md).

Autonomous agents run inside a microVM, not on the host. `orchestration/spawn.py`
launches each mission in one Apple `container` microVM (`botfiles-agent` image);
every agent attaches as a `container exec` process. The guest sees only that
mission's working copy (mounted at `/work`, writable) plus outbound network - the
host `$HOME`, SSH keys, and other repos are behind the VM's kernel boundary.
Harness credentials (claude Keychain OAuth, codex `auth.json`) are injected
read-only so agents can reach the model APIs.

Each mission gets its own local git clone on branch `mission-<feature>`, so
parallel missions on the same repo don't clobber each other; `spawn.py down`
fetches that branch back into your repo before removing the clone (and keeps the
clone if the fetch fails, so committed work is never lost).

```bash
bash sandbox/build.sh                              # install container, build the image (idempotent)
python3 orchestration/spawn.py up <roster.json>    # sandboxed by default
BOTFILE_NO_SANDBOX=1 python3 orchestration/spawn.py up <roster.json>   # bare host (debug only)
```

Open by design (tighten later if the threat model needs it): egress is open NAT,
and all agents in one mission share the VM. See `.botfile/memory/tools/sandbox.md`.

### Model proxy

`spawn.py up` also starts a per-mission [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI)
on the host and points every claude and codex agent at it. The fleet then
round-robins across every logged-in subscription account and Vercel AI Gateway, and a
roster `model` can name any upstream (`gpt-5.5` on a claude harness, `kimi-k3`,
`glm-5.3`). AI Gateway model aliases live in `orchestration/cliproxy.json`. With no
accounts and no key, the proxy stays off and agents use their own logins.

```bash
brew install cliproxyapi
cliproxyapi -claude-login      # once per Claude account
cliproxyapi -codex-login       # once per ChatGPT account
export AI_GATEWAY_API_KEY=...  # optional, Vercel AI Gateway
```

The model proxy routes Claude and Codex roles; Pi roles use their own provider configuration.

[Back to the README](../README.md)
