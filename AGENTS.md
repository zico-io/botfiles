# AGENTS.md — portable agent behavior (SSOT)

**Agent:** `gilbert` — 24/7 product agent
with persistent, portable memory.

## Operating principles

- **Distilled, not raw.** Store extracted facts (source + date + why), never
  conversation transcripts.
- **Provenance required.** Every fact carries `<source: …, date>`.
- **Upsert, not append-only.** Update and delete are allowed; stale facts get
  corrected, not accumulated.
- **No em dashes.** Use a plain dash "-" instead of "—".
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

## Orchestration protocol

Multi-agent work runs on **herdr** (placement/process/status) + the **`orbal-net`
CLI** talking to a per-mission **orbal-net server** on the host (coordination). Max
**three layers**, enforced by room membership:

- **L1 orchestrator** — the pane you are in. Talks to leads in `mission-<feature>`.
- **L2 leads** — one herdr tab each; in `mission-<feature>` and own `squad-<lead>`.
- **L3 workers** — split into their lead's tab; in `squad-<lead>` only. Leaves —
  never spawn.

Rooms are public, joined by name. The orchestrator never messages a worker
directly. Stand up / tear down a fleet from a roster with
`orchestration/spawn.py` (`up`/`down`) or the `/spawn-team` command; `up` starts
the mission's orbal-net server and `down` kills it (rooms die with it). A roster is a
catalog of teams: the orchestrator spawns only the team(s) a mission needs (pass
lead roles to `up`, or omit for all), not the whole roster every time. Harnesses
are claude/codex/pi. See `.botfile/memory/tools/orchestration.md`.

Agents emit typed progress with `orbal-net event <room> <kind>` / `orbal-net progress
<room> N/M` (kinds: task-start/done/error/abort, step, phase, blocked, handoff) so
an observer can follow the fleet in `orbal-net tui` - a live room-thread drill-in plus
a per-agent progress panel. Events are non-consuming (a separate table, they never
advance a read cursor), so monitoring never eats a message an agent still needs.

## Entity discipline

Canonical records live in `.botfile/entities/entities.jsonl`, one JSON object
per line. Refer to entities by `canonical_id`; add new names as `aliases`,
never a duplicate record.

    {"canonical_id":"ent_0001","name":"…","type":"…","aliases":[],"source":"…","date":"YYYY-MM-DD"}
