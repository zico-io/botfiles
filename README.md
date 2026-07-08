# botfile

A portable agent-memory layer. The authoritative state is git-tracked Markdown +
JSONL — the single source of truth (SSOT). There is no vector store: the memory
tree is small enough that `grep` searches it instantly. Add retrieval when grep
actually hurts, not before.

## Layout

```
AGENTS.md                     # SSOT — Codex + Pi read natively, Claude via import
CLAUDE.md                     # thin importer: "@AGENTS.md" + Claude-only extras
bin/botfile                   # CLI (validate / budget-check / wire / selfcheck)
.botfile/
  botfile.yaml                # manifest
  memory/
    index.md                  # one line per memory file — loaded first
    general.md                # cross-project curated facts
    domain/{topic}.md         # distilled domain knowledge
    tools/{tool}.md           # CLI patterns, configs, workarounds
  entities/entities.jsonl     # canonical entities + aliases
.github/workflows/botfile.yml # CI: selfcheck + validate + budget-check
```

Facts are distilled, never raw transcripts, and each carries inline provenance:

    - <fact> <source: …, YYYY-MM-DD>

## CLI

```bash
bin/botfile validate        # entities.jsonl schema, index completeness, provenance
bin/botfile budget-check    # root instruction files stay under the line budget
bin/botfile wire --tool T   # point a harness at this repo's AGENTS.md (T = codex|pi|claude|all)
bin/botfile selfcheck       # unit-check the provenance parser
```

`validate` asserts: every `entities.jsonl` line is valid JSON with the required
fields and a unique `canonical_id`; `memory/index.md` lists exactly the memory
files that exist; every fact bullet carries `<source: …, date>`.

## Wiring a harness

`bin/botfile wire` runs these for you; shown here for reference. All three
converge on the same `AGENTS.md`.

- **Codex** — `~/.codex/AGENTS.md` symlinked to this repo's `AGENTS.md`.
- **Pi** — `~/.pi/agent/AGENTS.md` symlinked to this repo's `AGENTS.md`.
- **Claude Code** — reads only `CLAUDE.md`, so `~/.claude/CLAUDE.md` is written as
  `@<repo>/AGENTS.md` (absolute path, since Claude walks up from cwd). An existing
  file is backed up to `CLAUDE.md.bak` first.

Per-repo, a root `CLAUDE.md` importing `@AGENTS.md` is **mandatory** for Claude
Code — a repo with only `AGENTS.md` gives Claude Code zero instructions, silently.

## Sandbox

Autonomous agents run inside a microVM, not on the host. `orchestration/spawn.py`
launches each mission in one Apple `container` microVM (`botfiles-agent` image);
every agent attaches as a `container exec` process. The guest sees only the target
repo (mounted at `/work`, writable) plus outbound network — the host `$HOME`, SSH
keys, and other repos are behind the VM's kernel boundary. Harness credentials
(claude Keychain OAuth, codex `auth.json`) are injected read-only so agents can
reach the model APIs.

```bash
bash sandbox/build.sh                              # install container, build the image (idempotent)
python3 orchestration/spawn.py up <roster.json>    # sandboxed by default
BOTFILE_NO_SANDBOX=1 python3 orchestration/spawn.py up <roster.json>   # bare host (debug only)
```

Open by design (tighten later if the threat model needs it): egress is open NAT,
and all agents in one mission share the VM. See `.botfile/memory/tools/sandbox.md`.

## What's deliberately not here

The original plan called for a derived vector/graph store, an embedding build
step, and an MCP `search` server. Skipped on purpose: with a handful of markdown
files, grep is faster to run and to reason about than an embedding cache. If the
memory tree grows past the point where grep hurts, add `bin/botfile build` + an
MCP `search` interface then — the SSOT is already structured to rebuild from.
