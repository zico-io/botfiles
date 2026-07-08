# Smoke test — orchestration harness

Live end-to-end check that a fleet spawns, coordinates over the comms server, and
tears down. Run from an orchestrator pane inside herdr (`HERDR_ENV=1`). Cheap: two
`sonnet` claude agents.

Paste this as the prompt:

---

Run the orchestration smoke test with `orchestration/smoke.roster.json` (feature
`smoke`: `lead-a` + `worker-a-1`, both claude/sonnet). Do each step and report
pass/fail:

1. **Self-check the server.** `python3 orchestration/comms_server.py --demo` prints
   `demo ok`. **PASS** on exit 0.
2. **Spawn.** `python3 orchestration/spawn.py up orchestration/smoke.roster.json`.
   Expect a printed `{role: pane_id}` map, and `mission.json`
   (`/tmp/botfile-missions/smoke/mission.json`) to carry `comms_url`,
   `comms_token`, `comms_pid` with the server process alive. **PASS** if
   `herdr pane list` shows a `mission-smoke` workspace with a `lead-a` tab and a
   worker split, and the server pid is running.
3. **Point your comms at the server + check in.** Export the coordinates from
   `mission.json`: `export COMMS_URL=<comms_url> COMMS_TOKEN=<comms_token>
   COMMS_AGENT=orchestrator`. Then `comms agents` shows `lead-a` and `worker-a-1`
   registered, and `comms read mission-smoke` shows `lead-a` ready. **PASS** if
   both registered.
4. **Delegate.** `comms send mission-smoke "lead-a: have worker-a-1 write the file
   smoke-ok.txt containing OK, then confirm."` Agents aren't pushed messages, so
   wake the target: `python3 orchestration/spawn.py poke smoke lead-a` (and, if the
   worker went idle before the task was posted, `... poke smoke worker-a-1`).
   **PASS** when `smoke-ok.txt` exists in the repo and the confirmation lands in
   `squad-lead-a` (`comms read squad-lead-a`). Confirm the orchestrator is **not**
   a member of `squad-lead-a` (`comms rooms` — hierarchy holds).
5. **Cross-host transport.** From a second shell with `COMMS_URL` = the mission's
   advertised IP:port and the same token, `COMMS_AGENT=probe comms send mission-smoke
   hello`; then `comms read mission-smoke` (as orchestrator) shows it. **PASS** if
   the message lands — proves TCP works off-loopback.
6. **Auth.** `COMMS_TOKEN=wrong comms rooms` fails (401). **PASS** on nonzero exit.
7. **Layer guard.** `python3 orchestration/spawn.py selfcheck` prints
   `selfcheck ok`. **PASS** on exit 0.
8. **Teardown.** `python3 orchestration/spawn.py down smoke` — kills the comms
   server (all rooms vanish with it) and closes the workspace. **PASS** when
   `herdr workspace list` no longer shows `mission-smoke`, the recorded
   `comms_pid` is gone, and `comms rooms` can no longer reach the server. Delete
   `smoke-ok.txt`.

If a pane's agent never reaches ready, `herdr pane read <pane> --source recent`
to see why. If the ready-match is wrong, tune `HARNESSES[...]["ready"]` in
`orchestration/spawn.py`. If an agent sits idle after a task is posted, that is
the no-push behavior of comms — `poke` it so it polls `comms inbox`.
