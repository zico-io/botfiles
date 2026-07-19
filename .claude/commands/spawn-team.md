---
description: Stand up and drive a 3-layer agent fleet on herdr for a roster
argument-hint: <roster.json>
---

You are the **orchestrator** (layer 1) for the mission described in `$ARGUMENTS`
(a roster JSON — see `orchestration/roster.example.json`). Require `HERDR_ENV=1`;
if unset, stop and say you are not inside herdr.

Read the roster to learn its `feature`. Then:

If the mission goal is ambiguous, stop and run `/scope-mission <feature>` first - it
interviews the human, writes `orchestration/<feature>.brief.md`, and drafts this roster.
`up` then auto-posts that brief into the `mission-<feature>` room as its first message
(each lead reads and relays it), so no manual brief step is needed here.

0. **Pick the teams.** The roster is a *catalog* — each layer-2 lead is one team,
   and its workers come with it. From the mission goal, decide the **minimum** set
   of teams you actually need; do not spawn teams the mission won't use. If the
   goal is ambiguous, ask the human which teams; only when it genuinely spans the
   whole fleet do you spawn all. Pass the chosen leads to `up` (comma-separated);
   omit the argument to spawn the whole roster.

1. **Spawn the fleet.** Run (append your chosen teams, or omit for all):
   `python3 orchestration/spawn.py up $ARGUMENTS <team1,team2>`
   It starts the mission's **orbal-net server** on the host, creates the
   `mission-<feature>` herdr workspace, launches every lead (layer 2, one tab
   each) and worker (layer 3, split into its lead's tab), and injects each
   agent's bootstrap so it `orbal-net join`s its room. It prints `{role: pane_id}` —
   keep this map, and records `orbal_net_url`/`orbal_net_token` in `mission.json`.

2. **Point your own `orbal-net` at the server.** Export the mission's coordinates so
   your `orbal-net` calls reach it as the orchestrator (read them from
   `/tmp/botfile-missions/<feature>/mission.json`):
   `export ORBAL_NET_URL=<orbal_net_url> ORBAL_NET_TOKEN=<orbal_net_token> ORBAL_NET_AGENT=orchestrator`
   Then `orbal-net create-room mission-<feature>` (you own it) — or the leads' first
   `orbal-net join` auto-creates rooms on demand; either way you are the mission-room
   owner if you create it first.

3. **Wait for the fleet to check in.** Poll `orbal-net peek mission-<feature>` until
   every lead has announced ready (leads relay their own workers' readiness).
   `orbal-net agents` shows who has registered. Monitor with `peek` (non-consuming),
   never `read` - `read` advances your cursor and eats messages the agents still need.

4. **Drive.** Post each task to the relevant lead with
   `orbal-net send mission-<feature> <task>`. Leads own their `squad-<lead>` room and
   delegate to workers there — **you never message workers directly** (that
   boundary is the 3-layer rule). Agents don't get pushed messages, so after
   posting a task wake the target: `python3 orchestration/spawn.py poke <feature>
   <role>`. Monitor with `herdr wait agent-status <pane> --status done` (panes
   from the map) and `orbal-net peek` / `orbal-net events` (both non-consuming - do
   not use `read` to monitor). Use `orbal-net dm <agent> ...` only to escalate.

   **GitHub bridge.** Spawned agents have no `gh`/network and their clone's origin is a
   local mirror, so the orchestrator bridges every live GitHub step (push, PR, release
   edits, repo settings). Have agents *prepare* GitHub artifacts as files/text and
   execute them yourself. To ship a mission branch as a PR, use
   `python3 orchestration/spawn.py bridge-pr <feature> [title]` (pushes
   `mission-<feature>` to the real remote and opens the PR via `gh`).

5. **Tear down** when the mission is complete:
   `python3 orchestration/spawn.py down <feature>` — this kills the orbal-net server
   (every room, mission and squad, dies with it) and closes the workspace. No
   manual room destruction is needed.

Never spawn a 4th layer; `spawn.py` rejects rosters that try. If a pane's agent
never reaches ready, read it with `herdr pane read <pane> --source recent` to
see why before retrying.
