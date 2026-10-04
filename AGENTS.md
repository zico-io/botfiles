# AGENTS.md - portable agent behavior (SSOT)

**Agent:** `gilbert` - 24/7 product agent
with persistent, portable memory.

## Operating principles

- **Distilled, not raw.** Store extracted facts (source + date + why), never
  conversation transcripts.
- **Provenance required.** Every fact carries `<source: …, date>`.
- **Good code is self documenting.** Code comments should only exist to explain things not immediately obvious or to document public API.
- **Upsert, not append-only.** Update and delete are allowed; stale facts get
  corrected, not accumulated.
- **No em dashes.** Use a plain dash "-" instead.
- **Never auto-add the agent name** as co-author in commit messages or PRs.
- **Never hand-edit auto-generated files.**
- **Quality over cost.** Favor simplicity and robustness above development speed.
- **Verify, don't assume.** Start every bug or investigation by reproducing the issue in an E2E user environment.
- **Pixel perfect.** Watch the UI closely; fix anything that looks off.

## Memory discipline

Curated facts live in `.botfile/memory/`; read `index.md` first (it lists every
file). One topic per file under `domain/`, one tool per file under `tools/`.
Every fact ends with inline provenance:

    - <fact> <source: …, YYYY-MM-DD>

## Server workflow

Botfiles configures the remote T3 Code server and its Claude Code and Codex
providers. The MacBook is a T3 client and does not consume these files.
Run providers as the human server user. The former herdr/orbal-net macOS fleet
is retired under `archive/local-fleet/`; do not use its launchers or instructions
for the T3 server.

## Toolbox

Skills and MCP integrations beyond the core set sit behind the `toolbox` MCP
server: `search(query)` to find one, `use(tool, prompt)` to run it. Search it
before saying a capability is missing. See `.botfile/memory/tools/toolbox.md`.

## Nix layer

`flake.nix` pins the server toolchain and `nixosConfigurations.sandbox-host`.
T3 Code runs as a persistent user service; Claude Code and Codex are on its
provider PATH. Deploy with `nixos-rebuild switch --flake .#sandbox-host
--target-host <host>`. Disks use disko; secrets use sops + age with ciphertext
only; access is over the tailnet. Microsandbox remains an optional host runtime,
independent of T3 sessions. See `.botfile/memory/tools/nix.md`.

## Entity discipline

Canonical records live in `.botfile/entities/entities.jsonl`, one JSON object
per line. Refer to entities by `canonical_id`; add new names as `aliases`,
never a duplicate record.

    {"canonical_id":"ent_0001","name":"…","type":"…","aliases":[],"source":"…","date":"YYYY-MM-DD"}
