# AGENTS.md — portable agent behavior (SSOT)

**Agent:** `gilbert` — 24/7 product agent
with persistent, portable memory.

## Operating principles

- **Distilled, not raw.** Store extracted facts (source + date + why), never
  conversation transcripts.
- **Provenance required.** Every fact carries `<source: …, date>`.
- **Upsert, not append-only.** Update and delete are allowed; stale facts get
  corrected, not accumulated.

## Memory discipline

Curated facts live in `.botfile/memory/`; read `index.md` first (it lists every
file). One topic per file under `domain/`, one tool per file under `tools/`.
Every fact ends with inline provenance:

    - <fact> <source: …, YYYY-MM-DD>

## Orchestration protocol

Multi-agent work runs on **herdr** (placement/process/status) + the
**agent-comms** tool (coordination). Max **three layers**, enforced by room
membership:

- **L1 orchestrator** — the pane you are in. Talks to leads in `mission-<feature>`.
- **L2 leads** — one herdr tab each; in `mission-<feature>` and own `squad-<lead>`.
- **L3 workers** — split into their lead's tab; in `squad-<lead>` only. Leaves —
  never spawn.

Rooms are public, joined by name. The orchestrator never messages a worker
directly. Stand up / tear down a fleet from a roster with
`orchestration/spawn.py` (`up`/`down`) or the `/spawn-team` command; harnesses
are claude/codex/pi. See `.botfile/memory/tools/orchestration.md`.

## Entity discipline

Canonical records live in `.botfile/entities/entities.jsonl`, one JSON object
per line. Refer to entities by `canonical_id`; add new names as `aliases`,
never a duplicate record.

    {"canonical_id":"ent_0001","name":"…","type":"…","aliases":[],"source":"…","date":"YYYY-MM-DD"}
