---
description: Stand up and drive a 3-layer agent fleet on herdr for a roster
argument-hint: <roster.json>
---

You are the **orchestrator** (layer 1) for the mission described in `$ARGUMENTS`
(a roster JSON — see `orchestration/roster.example.json`). Require `HERDR_ENV=1`;
if unset, stop and say you are not inside herdr.

Read the roster to learn its `feature`. Then:

0. **Pick the teams.** The roster is a *catalog* — each layer-2 lead is one team,
   and its workers come with it. From the mission goal, decide the **minimum** set
   of teams you actually need; do not spawn teams the mission won't use. If the
   goal is ambiguous, ask the human which teams; only when it genuinely spans the
   whole fleet do you spawn all. Pass the chosen leads to `up` (comma-separated);
   omit the argument to spawn the whole roster.

1. **Spawn the fleet.** Run (append your chosen teams, or omit for all):
   `python3 orchestration/spawn.py up $ARGUMENTS <team1,team2>`
   It starts the mission's **comms server** on the host, creates the
   `mission-<feature>` herdr workspace, launches every lead (layer 2, one tab
   each) and worker (layer 3, split into its lead's tab), and injects each
   agent's bootstrap so it `comms join`s its room. It prints `{role: pane_id}` —
   keep this map, and records `comms_url`/`comms_token` in `mission.json`.

2. **Point your own `comms` at the server.** Export the mission's coordinates so
   your `comms` calls reach it as the orchestrator (read them from
   `/tmp/botfile-missions/<feature>/mission.json`):
   `export COMMS_URL=<comms_url> COMMS_TOKEN=<comms_token> COMMS_AGENT=orchestrator`
   Then `comms create-room mission-<feature>` (you own it) — or the leads' first
   `comms join` auto-creates rooms on demand; either way you are the mission-room
   owner if you create it first.

3. **Wait for the fleet to check in.** Poll `comms read mission-<feature>` (or
   `comms inbox`) until every lead has announced ready (leads relay their own
   workers' readiness). `comms agents` shows who has registered.

4. **Drive.** Post each task to the relevant lead with
   `comms send mission-<feature> <task>`. Leads own their `squad-<lead>` room and
   delegate to workers there — **you never message workers directly** (that
   boundary is the 3-layer rule). Agents don't get pushed messages, so after
   posting a task wake the target: `python3 orchestration/spawn.py poke <feature>
   <role>`. Monitor with `herdr wait agent-status <pane> --status done` (panes
   from the map) and `comms read`. Use `comms dm <agent> ...` only to escalate.

5. **Tear down** when the mission is complete:
   `python3 orchestration/spawn.py down <feature>` — this kills the comms server
   (every room, mission and squad, dies with it) and closes the workspace. No
   manual room destruction is needed.

Never spawn a 4th layer; `spawn.py` rejects rosters that try. If a pane's agent
never reaches ready, read it with `herdr pane read <pane> --source recent` to
see why before retrying.
