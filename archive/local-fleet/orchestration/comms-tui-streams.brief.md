# Mission brief: comms-tui-streams

## Goal
Let an observer follow and understand a running fleet from `comms tui`: watch the
live back-and-forth in any room, and see structured progress (what each agent is
doing, how far along, what it is blocked on). Success = from one pane you can read
any room's live thread and tell the fleet's state at a glance, driven by real
events agents emit.

Context for a cold reader: `comms tui` already exists - a full-screen Rust
ratatui/crossterm monitor in `comms/src/tui/` that polls `agents`+`rooms` every
~1s and `peek`s each room. Today it shows only the latest message preview per
room, an agent roster (active/idle/busy/done), and server health. You cannot
follow the actual conversation, and there is no real progress signal. The message
model is `{seq, from, text}` with no timestamps and no event types; the server is
poll-only (SQLite/WAL + long-poll `wait`), no push.

## In scope
- TUI room thread drill-in: select a room, `Enter` to focus, scrollable
  live-updating history (via non-consuming `peek`, incremental since-seq), `Esc`
  back to the list.
- Server: a typed progress-event schema with server-set timestamps. Event kinds:
  task lifecycle (start/complete/error/abort), step/percent (N/M and/or %),
  phase/status label, blocked/waiting-on, handoff-to. Backward-compatible SQLite
  migration; add timestamps (events carry `ts`; add `ts` to messages while we are
  in there so the thread can show timing).
- Endpoint(s) to write and to read events non-consuming (monitor-safe, never
  advances a cursor).
- CLI: a new `comms progress` / `comms event` verb agents call to emit each kind,
  plus the read/peek path the TUI uses.
- TUI progress panel: per-agent current phase/step/percent, task state,
  blocked/handoff, live; and inline tagged event entries in the room thread.
- Adoption: update `spawn.py` bootstrap prompts and AGENTS / orchestration docs so
  leads and workers emit progress at natural points; demo end-to-end on a live
  smoke fleet.
- Extend `comms/smoke-tui.py` to cover drill-in and progress events.

## Non-goals
- No SSE/websocket/push transport rework - stay poll + long-poll.
- No consuming reads in the observer path - never advance agent cursors.
- No auth / multi-tenant / TLS changes.
- No rework of the existing room or agent-status model beyond adding events + timestamps.
- No web or GUI - terminal only.
- Not a general metrics/telemetry/analytics system; events exist for fleet monitoring.

## Constraints
- Rust. Reuse the comms crate HTTP client (`crate::http_post()`), serde types,
  ratatui 0.29 + crossterm 0.29. No new heavy dependencies.
- SQLite (WAL); keep append-only + per-room `seq`. Migration must not break an
  existing `comms.db` or older CLI callers.
- Observer stays read-only / non-consuming (`peek` semantics).
- Preserve terminal teardown safety (`TerminalGuard`) and the decoupled
  data/view thread model (`Arc<Mutex<Snapshot>>`).
- No em dashes in code/docs; stdlib-first in the Python orchestration layer.

## Acceptance criteria
- `comms tui`: select a room, `Enter`, see its full thread live-updating with
  scrollback; `Esc` returns to the list; observer cursors never advance
  (verified via `peek`-only path).
- Agents emit each event kind via the new CLI verb; events persist with
  timestamps and survive a server restart.
- TUI shows events inline in the thread AND in a dedicated progress panel
  (per-agent phase/step/percent/task-state/blocked/handoff), updating live.
- A live smoke fleet shows real emitted progress in the pane end-to-end.
- Extended `smoke-tui.py` passes; existing comms tests/gates stay green;
  migration works against a pre-existing db.

## Affected areas
- `comms/src/tui/{mod.rs,data.rs,view.rs}` - drill-in, progress panel, event
  polling into `Snapshot`.
- `comms/src/server.rs` - events table/columns, timestamps, endpoints.
- `comms/src/main.rs` - new CLI subcommand(s) + dispatch.
- `comms/smoke-tui.py` - extended coverage.
- `orchestration/spawn.py` - bootstrap prompts emit progress; optional helper to
  open the observer TUI pane.
- `AGENTS.md` + `.botfile/memory/tools/orchestration.md` - document the protocol.

## Risks and unknowns
- Schema migration against an existing `comms.db` without breaking older callers.
- Emission adoption: getting agents to emit reliably at the right moments without
  noise; needs a small, clear vocabulary and prompt wiring.
- Poll cost: full-thread + per-room event peeks every ~1s can get chatty; use
  incremental since-seq fetch and bounded history.
- TUI real-estate: fitting list + thread + progress + agents without clutter;
  likely needs view modes / toggles.
- Timestamp source (server clock on insert) and display (relative vs absolute).
- Events as a separate table/stream vs a message `kind` column - affects how
  cleanly events interleave in the drill-in thread.

## Team plan
- repo: `/Users/percules/.botfiles`
- **tui-lead** (claude/opus): owns end-to-end design and integration; defines the
  event vocabulary + schema/endpoint contract that both workers build against;
  owns adoption (spawn.py bootstrap + docs) and the live E2E smoke demo.
  - **worker-core** (claude/sonnet): server + CLI - events schema, migration,
    timestamps, endpoints, the `comms progress`/`event` verb, and the
    non-consuming event read path.
  - **worker-ui** (claude/sonnet): TUI - room thread drill-in with scrollback,
    progress panel, inline event rendering, keybindings, wired into the
    data/view threads; extend `smoke-tui.py`.
