---
description: Stand up and drive a 3-layer agent fleet on herdr for a roster
argument-hint: <roster.json>
---

You are the **orchestrator** (layer 1) for the mission described in `$ARGUMENTS`
(a roster JSON — see `orchestration/roster.example.json`). Require `HERDR_ENV=1`;
if unset, stop and say you are not inside herdr.

Read the roster to learn its `feature`. Then:

1. **Register + open the mission room.** Via the agent-comms tool: `register` as
   `orchestrator`, then `create_room` `mission-<feature>` (public).

2. **Spawn the fleet.** Run:
   `python3 orchestration/spawn.py up $ARGUMENTS`
   It creates the `mission-<feature>` herdr workspace, launches every lead
   (layer 2, one tab each) and worker (layer 3, split into its lead's tab),
   and injects each agent's bootstrap so it registers into agent-comms and
   joins its room. It prints `{role: pane_id}` — keep this map.

3. **Wait for the fleet to check in.** Poll agent-comms `read_room`
   `mission-<feature>` until every lead has announced ready (leads relay their
   own workers' readiness). `list_agents` shows who has registered.

4. **Drive.** Post each task to the relevant lead in `mission-<feature>`. Leads
   own their `squad-<lead>` room and delegate to workers there — **you never
   message workers directly** (that boundary is the 3-layer rule). Monitor
   progress with `herdr wait agent-status <pane> --status done` (panes from the
   map) and `read_room`. Use a DM only to escalate a stuck agent.

5. **Tear down** when the mission is complete:
   `python3 orchestration/spawn.py down <feature>` (closes the workspace), then
   agent-comms `destroy_room` for `mission-<feature>` and each `squad-*`.

Never spawn a 4th layer; `spawn.py` rejects rosters that try. If a pane's agent
never reaches ready, read it with `herdr pane read <pane> --source recent` to
see why before retrying.
