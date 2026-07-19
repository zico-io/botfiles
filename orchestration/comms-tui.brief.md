# Mission brief: comms TUI

## Goal
Give whoever is driving a fleet a live, at-a-glance view of mission comms without running
`comms` subcommands by hand. Ship a terminal UI for the existing `comms` CLI that loads in
a dedicated herdr pane. This replaces the abandoned per-harness status-line idea (only
Claude Code has a native status line; codex and pi do not), with one harness-agnostic
dashboard instead.

## In scope
- A new TUI mode on the comms CLI (e.g. `comms tui` / `comms watch`), reusing the existing
  HTTP client and JSON types in `comms/src/main.rs`. One binary, one new subcommand.
- Live display of:
  - mission + room identity (rooms this observer sees, mission name).
  - server health: connected / disconnected, inferred from request success (there is no
    dedicated health endpoint).
  - latest message preview: sender + snippet, per room.
  - agent roster with state (active / idle / busy / done) from `comms agents`.
  - unread / recent message counts per room.
- Live refresh: periodic poll of agents/rooms plus the existing `comms wait` long-poll for
  new messages where practical.
- Launchable in a herdr pane via a documented one-liner; reads `COMMS_URL` / `COMMS_TOKEN`
  / `COMMS_AGENT` from the environment exactly like every other comms client.
- Graceful server-down handling: show disconnected, keep retrying, recover without crash;
  clean terminal teardown on quit.

## Non-goals
- No per-harness status-line hooks (Claude statusLine script, codex, pi) - explicitly dropped.
- No changes to comms protocol, auth, or transport.
- No new comms server endpoints unless a spike proves the existing read commands
  (whoami / agents / rooms / inbox / wait) cannot drive the view.
- Not a chat client / message composer - read-only dashboard. Sending is out of scope
  unless it falls out for free.
- No change to how spawn.py injects env vars or launches harnesses, beyond an OPTIONAL
  documented helper to open the TUI pane.

## Constraints
- Rust. Reuse the existing comms crate, its HTTP client, and its serde JSON types
  (`comms/src/main.rs`, `comms/src/server.rs`). Do not fork a separate tool or language.
- Prefer stdlib and already-present deps. If a TUI framework is warranted, ratatui +
  crossterm is the idiomatic Rust choice; a plain ANSI alt-screen redraw loop is acceptable
  if it covers the need. Lead decides, leanest option that works.
- Discovery strictly via `COMMS_URL` / `COMMS_TOKEN` / `COMMS_AGENT` env vars. No new config file.
- Must not regress existing comms subcommands or `cargo test` in the comms crate.
- Repo conventions: no em dashes, use `-`.

## Acceptance criteria
- `comms tui` (or chosen name) launches a full-screen dashboard against a running mission
  comms server and shows mission/rooms, per-agent state, unread/recent counts, and the
  latest message preview, refreshing live as messages arrive and agent states change.
- Server-down is shown clearly and the TUI recovers when the server returns (no crash, no
  garbled terminal).
- Runs cleanly in a herdr pane with a documented launch command; quits cleanly (q / Ctrl-C)
  and restores the terminal.
- `cargo build --release` succeeds and existing `cargo test` stays green.
- Demonstrated end-to-end against the smoke-test mission: spawn a small fleet, watch agent
  states and messages update live in the TUI.

## Affected areas
- `comms/src/main.rs` (add subcommand + client reuse); likely a new `comms/src/tui.rs`
  module; `comms/Cargo.toml` (deps only if ratatui/crossterm are added).
- `orchestration/spawn.py` and spawn-team docs ONLY if we add an optional helper/pane to
  auto-open the TUI. Keep minimal.
- `.botfile/memory/tools/orchestration.md` - document the TUI as a coordination surface.

## Risks and unknowns
- Refresh cadence vs. server load; `comms wait` long-poll is per-room and must be
  multiplexed across rooms. Spike this first.
- Server health has no dedicated endpoint - must be inferred from request success / exit
  code. Define the exact signal before building the indicator.
- ratatui as a new dependency vs. a lean redraw loop - decide from actual interaction needs
  (scrolling, multi-pane). Default lean.
- A full-screen alt-screen TUI cohabiting with herdr's own pane rendering - verify redraw
  and resize behave inside a herdr pane.
- Observer identity: the TUI pane is not a mission agent. `comms inbox` is per-calling-agent,
  so an observer wants global reads (agents/rooms are global; use peek/read per room for
  message previews) and should NOT pollute the agent roster with a fake identity. Decide the
  observer's read strategy early.

## Team plan
- tui-lead (claude/opus): owns the comms TUI end to end - subcommand and module layout,
  integrates the two workstreams, runs the E2E smoke demo, keeps existing comms tests green.
  - worker-core (claude/sonnet): data layer. Reuse the comms HTTP client to fetch
    whoami/agents/rooms and per-room message previews; add polling plus `comms wait`
    long-poll multiplexing; model server-health and reconnect; expose a refreshing snapshot
    the UI renders.
  - worker-ui (claude/sonnet): rendering and interaction. Full-screen layout (identity,
    rooms, agent states, unread/recent counts, latest-message preview), keybindings
    (quit/scroll), clean terminal teardown, and the documented herdr-pane launch one-liner.
