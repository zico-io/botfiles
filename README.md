# botfiles

Portable agent instructions, curated memory, and tooling for Claude Code and Codex
running on the remote T3 Code server. Git-tracked Markdown and JSONL hold the
authoritative state.

## Quick start

Use Python 3 directly, or enter the pinned toolchain with Nix:

```bash
nix develop
./bin/botfile selfcheck
./bin/toolbox selfcheck
./bin/sync-skills --check
./bin/botfile validate
./bin/botfile budget-check
```

The CLIs use only the Python standard library. `nix develop` also supplies the
Node, GitHub, and secrets tooling used by the rest of the repo.

## Harness setup

Link the shared instructions into your installed harnesses:

```bash
./bin/botfile wire --tool all  # codex | claude | all
```

This symlinks `AGENTS.md` into `~/.claude/` and `~/.codex/`.
Run `bash provision.sh` on the server to register the toolbox in both providers.
The MacBook is a T3 client and does not install or consume botfiles.

Nix deploys the `botfiles` package and shared instructions to both server logins.
Run `botfiles-provision` once as each user to register the packaged toolbox.
For local skill development and fleet deployment, see [shared skills](docs/skills.md).

## Repository layout

| Path | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Shared agent instructions |
| [.botfile/](.botfile/) | Manifest, curated memory, and canonical entities |
| [bin/](bin/) | Memory CLI, toolbox, and shared skill synchronization |
| [skills/](skills/) | Reusable workflows |
| [toolbox/catalog.json](toolbox/catalog.json) | Skill roots, plugins, and MCP integrations |
| [flake.nix](flake.nix) | Pinned dev toolchain, checks, packages, and NixOS host |
| [hosts/](hosts/), [modules/](modules/), [pkgs/](pkgs/) | NixOS host configuration and sandbox runtime |
| [secrets/](secrets/) | Sops configuration and secret provisioning instructions |

## Memory and validation

Read [.botfile/memory/index.md](.botfile/memory/index.md) first. Store distilled
facts, each with inline provenance:

```text
- <fact> <source: source name, YYYY-MM-DD>
```

Use one file per domain topic or tool. Keep entities in
[entities.jsonl](.botfile/entities/entities.jsonl), referring to each by its
`canonical_id` and adding alternate names as aliases.

`validate` checks entity fields and unique IDs, memory index completeness, and
fact provenance. `budget-check` enforces the root instruction line budget.
`selfcheck` exercises the provenance parser; the toolbox has its own selfcheck.
CI runs these gates and evaluates the Nix flake and sandbox host. Run
`nix flake check` for the flake checks.

The retired macOS fleet and its mission history live in [archive/](archive/README.md).

## Operating guides

- [Toolbox](docs/toolbox.md): search and use skills and MCP integrations.
- [Nix and sandbox-host](docs/nix.md): deploy the remote KVM host and manage T3 Code.
- [Shared skills](docs/skills.md): edit locally and sync deployable fleet copies.
- [Secrets](secrets/README.md): provision encrypted host secrets.
