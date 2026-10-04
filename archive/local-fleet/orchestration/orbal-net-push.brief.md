# Mission brief: orbal-net-push

Long name: "rewrite orbal-net's backend to use push not poll"

## Goal
Replace orbal-net's poll-based message/event delivery with a server-push model.
Today the `orbal-net serve` backend delivers coordination traffic by polling: agents
block on a `wait` long-poll (Condvar + a 2s backstop re-check) and re-issue it in a
loop, and the TUI hot-polls the server every interval via `data.rs`. The server should
instead push new messages and progress events to subscribed clients over a persistent
stream, so clients react on arrival with no timer loop. Success: agents and the TUI
receive messages/events through a single SSE stream, the interval poller and the
`wait`/backstop loops are gone, and a live mission coordinates end-to-end with lower
latency and no polling.

## In scope
- New SSE (Server-Sent Events) streaming endpoint on the existing tiny_http server:
  a client subscribes and the server pushes each new message + progress event as it
  lands. Chunked HTTP, no new dependency.
- Server-side notify: reuse/extend the existing Condvar so a `send`/`dm`/`event`
  wakes subscriber threads and flushes the new rows to their streams. Remove the 2s
  backstop re-check from the wait path - wakeups become pure notify.
- Reconnect + backfill: the stream accepts a `since` cursor (Last-Event-ID style) so a
  reconnecting client resumes exactly after its last received row and loses nothing.
  This preserves the "monitoring never eats a message an agent still needs" guarantee.
- New agent-facing CLI command (`orbal-net stream`/`recv`, name is a lead decision)
  backed by SSE, replacing the `wait` command. Remove `wait` and its long-poll loop.
- TUI: rewrite `src/tui/data.rs` to consume the SSE stream instead of the interval
  poller; keep the Snapshot/view contract stable so `view.rs` is untouched where
  possible. Drop the `--interval` poll cadence (or repurpose it as a reconnect backoff).
- Keep one-shot `read`/`peek`/`inbox` ops for catch-up, scripting, and `peek`-style
  monitoring. Read stays cursor-advancing, peek stays non-consuming, as today.
- Update `spawn.py`, `AGENTS.md`, `.botfile/memory/tools/orchestration.md`, and any
  docs/commands that reference `wait` or the poll interval to the new stream command.

## Non-goals
- No change to the coordination semantics: room model, three-layer membership, cursor
  consumption rules (read advances, peek/events do not), wire message shape.
- No move to WebSocket or any new networking dependency - SSE over tiny_http only.
- No new deps at all; keep the minimal set (tiny_http, rusqlite, serde_json, ratatui,
  crossterm). `cargo deny check` stays green.
- Not a rewrite of the SQLite store, auth (Bearer token), or the event vocabulary
  (the 8 progress-event kinds stay as-is).
- No feature changes to the TUI beyond the transport swap (same panels, same drill-in).
- Do not rename the binary, env vars, rooms, or protocol structural names.

## Constraints
- SSE over tiny_http: tiny_http is thread-per-request/blocking, so each open stream
  holds a worker thread. Design so a mission's worth of subscribers (single-digit to
  low-double-digit agents + observers) is fine; document the ceiling.
- Rust edition 2021, MSRV 1.78, `rust-toolchain.toml` pin - keep CI (fmt, clippy,
  test, coverage, deny, build) green.
- No message loss across reconnect: the `since` backfill must be exact - an agent that
  drops and reconnects must not miss or duplicate a message it hadn't read.
- The live orchestration substrate may be running on the current binary. Do not tear
  down or break a running mission server mid-flight; validate the new binary on a
  throwaway mission before it becomes the default.
- Ships to GitHub repo `zico-io/orbal-net`. Spawned agents have no `gh`/network and
  their clone's origin is a local mirror, so the orchestrator bridges every live
  GitHub step (push + PR via `spawn.py bridge-pr orbal-net-push`, release edits, repo
  settings). Agents prepare those artifacts as files/text for the orchestrator.

## Acceptance criteria
- A client subscribes to the SSE endpoint and receives new messages + events within
  the notify latency (no interval-length delay); no polling loop remains in agent or
  TUI code paths.
- The `wait` command and its long-poll loop, the 2s Condvar backstop, and the TUI
  interval poller are all removed (grep-clean).
- Reconnect test: kill and restart a subscriber mid-stream with a `since` cursor; it
  resumes with zero missed and zero duplicated messages.
- One-shot `read`/`peek`/`inbox` still behave exactly as before (cursor-advance vs
  non-consuming); existing server tests for them stay green, new tests cover the stream.
- `orbal-net --selfcheck` passes; `smoke-tui.py` passes against the SSE-backed TUI.
- A fresh `spawn.py up` on a throwaway mission stands up rooms and coordinates agents
  over the stream command end-to-end, validated before the old path is removed.
- CI green (fmt, clippy, test, coverage, deny, build); no new dependencies added.

## Affected areas
- `src/server.rs` - new SSE endpoint + route, notify/flush on send/dm/event, remove
  wait backstop, keep op_read/op_peek/op_inbox. (~1100 lines today.)
- `src/main.rs` - new `stream`/`recv` client command (SSE consumer over http_post's
  sibling GET/stream path), remove `wait` command.
- `src/tui/data.rs` - replace the background interval poller with an SSE consumer
  filling the shared Snapshot; `src/tui/mod.rs`/`view.rs` - drop poll-cadence config,
  keep Snapshot contract.
- `orchestration/spawn.py` - agent recv/wait invocation -> stream command.
- Docs/memory: `AGENTS.md`, `.botfile/memory/tools/orchestration.md`,
  `.claude/commands/spawn-team.md` (any `wait`/interval references).

## Risks and unknowns
- tiny_http streaming: confirm it can hold a connection open and write incremental
  chunks (SSE `data:` frames) without buffering the whole response. If it can't stream
  natively, the endpoint may need a raw-socket/chunked-writer path - investigate first.
- Thread-per-subscriber ceiling: many long-lived streams consume threads. Fine at
  mission scale; note the ceiling and the upgrade path (poll-based reactor) in a
  `ponytail:` comment rather than pre-building it.
- Cursor semantics on the stream: decide whether the agent stream auto-advances the
  read cursor or is peek-like with explicit ack. Must preserve "monitoring (events/peek)
  never eats a message an agent still needs." Lead fixes this contract before workers
  diverge.
- Reconnect/backfill correctness is the sharp edge - exact `since` resume, no gap at
  the notify/backfill boundary (race between "backfill up to N" and "live push from N").
- Live-substrate break: keep the old binary until the new one is validated on a
  throwaway mission.

## Team plan
- push-lead (claude/opus): owns the mission end-to-end; fixes the SSE wire contract
  (frame format, `since`/Last-Event-ID backfill, cursor-advance vs ack semantics) and
  the notify/backfill race boundary before workers diverge; sequences server before
  client/TUI; validates on a throwaway mission; relays human-only GitHub steps.
  - worker-server (claude/sonnet): SSE endpoint + route on tiny_http, notify/flush on
    send/dm/event, remove the wait op + 2s backstop, `since` backfill, keep one-shot
    read/peek/inbox, server tests including the reconnect/no-loss test.
  - worker-client (claude/sonnet): new `stream`/`recv` CLI command consuming SSE
    (replaces `wait`), rewrite `tui/data.rs` to fill the Snapshot from the stream, drop
    the interval poller/`--interval`, update `spawn.py` + docs/memory to the new command.
