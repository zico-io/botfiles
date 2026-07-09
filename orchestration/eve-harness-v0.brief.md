# Mission brief: eve-harness-v0

Long name: "convert one leaf-worker role to a local eve agent (the monkey-belay harness) and prove it in a live mixed fleet - eve-harness RFC S9 step 3"

## Goal
Build the first REAL eve-harness increment (RFC `orchestration/eve-harness.rfc.md`
section 9, step 3): take the proven PoC mechanic and productionize it as a standalone
harness repo called **monkey-belay**, then run ONE eve leaf-worker as a first-class
orbal-net agent side by side with claude/codex/pi workers in the same `squad-<lead>`
room. The thesis is already proven (PoC verdict: GO, do not re-litigate); v0 turns the
throwaway reference into production code and wires it into the fleet.

Scope decision (settled): the eve worker runs **LOCAL** - `eve start` in a herdr pane
inside the mission VM, with its connector alongside, sharing the LAN with orbal-net. A
local role shares the mission clone at `/work` exactly like a claude worker, so
`wcommit`/harvest just work, and it sidesteps both open gaps (public orbal-net
reachability and git write-back from a Vercel Sandbox). Deployed-to-Vercel is a later
increment (RFC S9 step 4+), explicitly NOT this mission.

Success = `orbal-net tui` / `peek` / `events` cannot tell the eve worker apart from a
claude worker - same room thread, same progress panel - and the eve worker produces
genuine commits/harvest from `/work` like its peers.

## In scope
The deliverable is TWO things: the harness repo (fleet work) and a prepared spawn.py
diff (orchestrator-applied).

**A. The `monkey-belay` repo** (new, `/Users/percules/dev/monkey-belay`, fresh empty
repo; workers port the PoC code in from `/Users/percules/dev/eve-harness` as reference
and harden it - do not rewrite from scratch, do not fork the PoC repo wholesale):
- A minimal eve project (`instructions.md`, `agent.ts` with a model via AI Gateway) that
  runs locally as a durable production server via **`eve start`** (NOT `eve dev` - see
  Constraints). Pinned eve version recorded.
- `channels/orbal-net.ts` - a webhook-style channel: `POST /orbal-net/message` takes one
  already-arrived frame `{room, agent, text, msgSeq, evtSeq}` and calls `send(text,
  {continuationToken: "orbal-net:<room>:<agent>"})` to mint/resume the turn. It injects
  `orbal-net-room: <room>` into the turn context so the agent replies to the right room.
  The channel does NOT hold the SSE open (a Function cannot).
- Native outbound tools `tools/orbal_net_send.ts`, `_event.ts`, `_progress.ts`: thin
  POSTs to the mission orbal-net server, emitting messages, the 8 event kinds
  (task-start/done/error/abort, step, phase, blocked, handoff), and `progress N/M` as
  runtime tool calls (no `orbal-net` CLI shell-out from the agent).
- The standalone **connector** process: holds one `orbal-net recv <room> --follow`
  subscription, POSTs each pushed frame to the channel webhook, and is the sole cursor
  owner. It joins the room AS the agent on startup (a non-member `/send` 403s). It
  serializes strictly per (room, agent): deliver one frame, wait for the session to park
  (`session.waiting`), fsync-commit its `<msgSeq>:<evtSeq>` cursor, then read the next
  frame; resumes with `--since` on restart; crash-restart safe; its liveness is
  observable.
- The eve role is a FIRST-CLASS orbal-net agent - its own identity, room membership, and
  cursor - never an eve subagent.
- A README: how to run the harness standalone and how spawn.py launches it.

**B. The spawn.py wiring** (a diff the lead DRAFTS as text; the orchestrator applies and
tests it against a live fleet, since spawning is L1-only):
- A new harness type `eve` launch path that runs `eve start` in a herdr pane (not the
  generic `HARNESSES` shell-command shape) with a ready/working banner signature.
- A connector lifecycle: `orbal_net_connector_up(feature)` symmetric to `orbal_net_up()`
  - detached, pid recorded in `mission.json`, killed by `down`, its liveness reported by
  `status`.
- `bootstrap()` is NOT needed for an eve role (the join/recv/emit protocol is compiled
  into the channel + tools, not re-taught by prompt). `poke` still applies to the local
  pane. `validate()`'s 3-layer/room rules are untouched.

**C. The demo** (orchestrator-run): a tiny throwaway scratch repo with a trivial
multi-part task, and a live mixed fleet with one eve leaf-worker beside claude/codex/pi
workers in one `squad-<lead>` room. A passing run is the acceptance evidence.

## Non-goals
- No DEPLOYED / Vercel role. No public orbal-net reachability work, no git write-back
  from a Vercel Sandbox. That is RFC S9 step 4+, not this mission.
- Not solving the git write-back gap (RFC S10 risk 1) - a LOCAL role moots it (it lives
  in the mission clone at `/work`).
- No eve subagents for the role - subagents have no identity/room/cursor and would break
  `peek`/`events`/tui monitoring.
- No changes to orbal-net itself (the Rust binary) or its protocol - consumed as-is.
- No `bootstrap()` first-turn prompt for the eve role.
- Not re-proving the three PoC proofs as the deliverable - they passed (VERDICT: GO).
  Carry their findings forward; do not re-litigate or rebuild the proof harness.
- Do not reinvent the PoC reference impls (`agent/channels/orbal-net.ts`,
  `tools/orbal_net_*.ts`, `connector/`) - port and harden them.
- No memory/entity writing; this is a work artifact.

## Constraints
- eve is a Vercel public beta (framework/APIs/behavior may change before GA). Pin the
  exact eve version (the PoC used `eve@0.22.1`) and record it; design to concepts, not
  signatures.
- Use **`eve start`** (built production server, port 3000) - it resumes durable sessions.
  **`eve dev`** (port 2000) does NOT resume durable sessions; do not conflate them. Wipe
  `.workflow-data` per local run (a real deployment gets a fresh store per deploy).
- The connector MUST serialize per (room, agent) with a park-gated, fsync'd cursor
  commit: eve does NOT durably queue concurrent deliveries to one continuation token, so
  concurrent frames cannot be fired at one session. This serialization is what makes
  zero-lost / zero-dup hold.
- Exactly-once = the connector's park-gated fsync'd cursor commit (durable authority) +
  the channel's in-memory msgSeq dedup guard (cheap extra layer).
- The agent's orbal-net identity must be a room member and must know which room (orbal-net
  rejects `/send` from a non-member with 403): the connector `/join`s the room as the
  agent on startup, and the channel injects `orbal-net-room: <room>`.
- Resume choreography (from the PoC): let a turn fully checkpoint before any kill; after a
  cold restart the session needs a beat to rehydrate (re-deliver if a frame lands too
  early).
- Preserve orbal-net semantics exactly: `recv --follow` / `peek` / `events` are
  non-consuming; the connector is the sole component that owns/advances the cursor; `read`
  advances the cursor. 3-layer room-membership rules untouched.
- Node 24 is the sandbox image default (eve requires `>=24`) - already baked, no in-VM
  workaround needed.
- Vercel credential proxy is already provisioned in the image (`mission_secrets()` copies
  the host cred to `/secrets/vercel.auth.json`; the entrypoint places it at the guest
  `~/.local/share/com.vercel.cli/auth.json`; in-VM `vercel whoami` -> `zico-io`). KEEP
  this. For the local eve project to call models via AI Gateway it needs a linked Vercel
  project + OIDC token: use `vercel link --yes --scope <team-slug> --project <name>`
  (links AND writes `.env.local` with a fresh `VERCEL_OIDC_TOKEN`). `npx eve link` needs a
  TTY and refuses non-interactive - do not use it. Host team is `zico-io`; a bare
  `vercel link --yes` lists valid slugs in its JSON error `choices[]`.
- The sandbox has open NAT egress, so in-VM `npm`, AI Gateway model calls, and
  `vercel link`/`deploy` work. The GitHub bridge is only about `gh`/origin-push.
- Two repos, one mission clone: the fleet target repo is `monkey-belay`. Spawned agents
  have no `gh`/network and their clone origin is a local mirror. The orchestrator bridges
  all live GitHub steps (monkey-belay repo create, push + PR via `spawn.py bridge-pr
  eve-harness-v0`) AND applies the prepared spawn.py diff to `.botfiles` and runs the demo
  mixed fleet (spawning is L1-only). Agents PREPARE the spawn.py diff as text; they cannot
  edit `.botfiles` from the monkey-belay clone.
- No em dashes anywhere; use "-". Stay consistent with today's terms (herdr panes/tabs,
  `mission-<feature>`/`squad-<lead>`, spawn `up`/`down`/`poke`/`status`/`bridge-pr`,
  orbal-net `recv`/`peek`/`event`/`progress`).

## Acceptance criteria
- `monkey-belay` runs standalone: `eve start` + the connector against a real orbal-net
  `recv`/SSE server; a message into the room mints an eve turn and the agent's
  `orbal_net_send`/`_event`/`_progress` land back in the room (the PoC Proof-1 mechanic,
  now as productionized code). Pinned eve version recorded.
- The eve agent is a first-class orbal-net room member: its identity shows in `orbal-net
  peek <room>`, its typed events in `orbal-net events`, its `progress N/M` in the tui
  per-agent panel - the same shape as a claude worker.
- The connector serializes per (room, agent), owns/advances the cursor, resumes with
  `--since` after a kill with zero lost / zero dup, is crash-restart safe, and its
  liveness is observable.
- The prepared spawn.py diff adds the `eve` harness launch path (`eve start` in a pane),
  the `orbal_net_connector_up`/`down`/`status` lifecycle (pid in `mission.json`), and
  leaves `bootstrap`/`validate`/`poke` correct. The orchestrator applies it; it passes
  `python3 orchestration/spawn.py selfcheck` and a real `up`/`down`.
- Demo: a live mixed fleet (one eve leaf-worker + at least one claude/codex/pi worker in
  the same `squad-<lead>` room) runs a trivial task on the scratch repo; `orbal-net tui` /
  `peek` / `events` cannot distinguish the eve worker from a claude worker in the room
  thread or the progress panel; the eve worker produces genuine commits/harvest from
  `/work` like its peers. Recorded evidence (tui/peek log + a commit).
- `status` surfaces connector liveness; `down` kills the connector and the pane; rooms
  die with the server.
- No em dashes; consistent vocabulary.

## Affected areas
- NEW repo `/Users/percules/dev/monkey-belay` (the deliverable; orchestrator git-inits
  before `up`; final GitHub repo bridged by orchestrator): the eve project
  (`instructions.md`, `agent.ts`, `channels/orbal-net.ts`, `tools/orbal_net_*.ts`), the
  connector process, README, tests.
- `.botfiles` (PREPARED diff only, orchestrator-applied): `orchestration/spawn.py`
  (`HARNESSES`/`eve` launch path, `orbal_net_connector_up`, `down`/`status`/`poke`
  wiring), plus any roster-schema note for harness `eve`.
- Reference (read, do NOT modify): `/Users/percules/dev/eve-harness` (the PoC - read
  `VERDICT.md` + `CONTRACT.md` first; sections 4 and 5 of CONTRACT are load-bearing; then
  `agent/`, `connector/`), `orchestration/eve-harness.rfc.md` (design of record - S5, S6,
  S7, S8, S9, S10), `.botfile/memory/tools/orchestration.md`, `.botfile/memory/tools/sandbox.md`.
- The orchestrator drops the PoC `CONTRACT.md` + relevant RFC sections into the mission
  clone (the fresh monkey-belay repo will not carry them by default), the way the PoC
  mission had its RFC dropped in.

## Risks and unknowns
- `eve start` vs `eve dev`: confirm `eve start` (built server) is the right local runtime
  and that a running local role resumes durable sessions across a pane restart within a
  mission. Do not use `eve dev`.
- The connector is a new always-on dependency whose failure is SILENT (rooms keep working,
  the eve agent just stops receiving). It must be crash-restart-safe (it is, in the PoC)
  and `status` must surface its liveness.
- The eve launch path differs from the generic `HARNESSES` shell-command shape (`eve
  start` is a long-lived server plus a connector sidecar): the pane readiness banner and
  the working-state match for `eve start` are unknown and need a `ready`/`working`
  signature like the other harnesses.
- AI Gateway / OIDC token lifetime for a long-running local role: `vercel link` writes a
  `VERCEL_OIDC_TOKEN` into `.env.local`; confirm it stays valid for the mission duration
  (refresh behavior unknown).
- Two-repo coordination: the spawn.py diff is drafted blind to a live fleet (agents cannot
  spawn), so the orchestrator is the first to run it end to end - budget an apply + debug
  loop before the demo passes.
- Beta churn in eve / AI SDK 7 mid-mission; pin versions and record them.
- Identity/membership: the connector must `/join` the room as the agent before `/send`
  (403 otherwise) and the channel must inject `orbal-net-room` - get these first-class or
  `peek`/`events`/tui monitoring breaks.

## Team plan
- repo: `/Users/percules/dev/monkey-belay` (new; orchestrator git-inits before spawn)
- **belay-lead** (claude/opus): owns `monkey-belay` end to end. Ports the PoC code in as
  the starting reference, sets the productionized channel/tools/connector contract and the
  `eve start` durable-run shape before the workers diverge, makes the eve role a
  first-class orbal-net agent (identity/room/cursor), integrates both workers into one
  runnable harness, writes the README, DRAFTS the spawn.py `eve`-launch-path +
  connector-lifecycle diff as text for the orchestrator to apply, and prepares the GitHub
  repo-create / PR requests. Relays the human-only bridge steps.
  - **worker-harness** (claude/sonnet): the eve agent side - `instructions.md`, `agent.ts`
    (model via AI Gateway, `vercel link`/OIDC), `channels/orbal-net.ts` (webhook frame ->
    `send` with the `orbal-net:<room>:<agent>` continuation token, `orbal-net-room`
    injection, room-join-as-agent), and the outbound tools
    `orbal_net_send`/`_event`/`_progress` (all 8 event kinds + `progress N/M`). Makes it
    runnable and durable under `eve start`. Ports and hardens from the PoC `agent/`.
  - **worker-connector** (claude/sonnet): the standalone connector - one `recv <room>
    --follow` per (room, agent), strict per-(room, agent) serialization (deliver, wait for
    park, fsync cursor, next), `--since` resume, crash-restart safe, observable liveness.
    Ports and hardens from the PoC `connector/`.
