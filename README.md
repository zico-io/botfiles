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
./bin/botfile validate
./bin/botfile budget-check
```

The CLIs use only the Python standard library. `nix develop` also supplies the
Node and GitHub tooling used by the rest of the repo.

## Harness setup

Link the shared instructions into your installed harnesses:

```bash
./bin/botfile wire --tool all  # codex | claude | all
```

This symlinks `AGENTS.md` into `~/.claude/` and `~/.codex/`.
Run `bash provision.sh` on the server to register the toolbox in both providers.
The MacBook only registers the toolbox from a checkout, with the same command.

For local skill development and fleet deployment, see [shared skills](docs/skills.md).

## Repository layout

| Path | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Shared agent instructions |
| [.botfile/](.botfile/) | Manifest, curated memory, and canonical entities |
| [bin/](bin/) | Memory CLI and toolbox |
| [skills/](skills/) | Reusable workflows |
| [toolbox/catalog.json](toolbox/catalog.json) | Skill roots, plugins, and MCP integrations |
| [flake.nix](flake.nix) | Pinned dev toolchain and checks |

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
CI runs these gates and evaluates the Nix flake. Run
`nix flake check` for the flake checks.

## Operating guides

- [Toolbox](docs/toolbox.md): search and use skills and MCP integrations.
- [Nix](docs/nix.md): the dev shell and flake checks.
- [Shared skills](docs/skills.md): where Bask skills come from and how to edit them.
