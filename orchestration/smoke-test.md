# Smoke test — orchestration harness

Live end-to-end check that a fleet spawns, coordinates over the comms server, and
tears down. Run from an orchestrator pane inside herdr (`HERDR_ENV=1`). Cheap: two
`sonnet` claude agents.

Paste this as the prompt:

---

Run the orchestration smoke test with `orchestration/smoke.roster.json` (feature
`smoke`: `lead-a` + `worker-a-1`, both claude/sonnet). Do each step and report
pass/fail:

1. **Self-check the server.** `comms --selfcheck` prints `comms selfcheck ok`
   (or, from source, `cd comms && cargo test`). **PASS** on exit 0.
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
   both registered. (`up` already created `mission-smoke` owned by `orchestrator`,
   so you are a member and can `comms send` without a manual `join`.)
4. **Delegate.** `comms send mission-smoke "lead-a: have worker-a-1 write the file
   smoke-ok.txt containing OK and commit it, then confirm."` Agents aren't pushed
   messages, so wake the target: `python3 orchestration/spawn.py poke smoke lead-a`
   (and, if the worker went idle before the task was posted, `... poke smoke
   worker-a-1`). The worker writes+commits inside its isolated mission clone, so
   **PASS** when `smoke-ok.txt` exists at `/tmp/botfile-missions/smoke/work/`
   (`git -C /tmp/botfile-missions/smoke/work log --oneline` shows the worker's
   commit) and the confirmation lands in `squad-lead-a` (`comms read
   squad-lead-a`). Confirm the orchestrator is **not** a member of `squad-lead-a`
   (`comms rooms` — hierarchy holds).
5. **Cross-host transport.** From a second shell with `COMMS_URL` = the mission's
   advertised IP:port and the same token, `COMMS_AGENT=probe comms send mission-smoke
   hello`; then `comms read mission-smoke` (as orchestrator) shows it. **PASS** if
   the message lands — proves TCP works off-loopback.
6. **Auth.** `COMMS_TOKEN=wrong comms rooms` fails (401). **PASS** on nonzero exit.
7. **Layer guard.** `python3 orchestration/spawn.py selfcheck` prints
   `selfcheck ok`. **PASS** on exit 0.
8. **Teardown.** `python3 orchestration/spawn.py down smoke` — kills the comms
   server (all rooms vanish with it), harvests the `mission-smoke` branch back into
   the repo, and closes the workspace. **PASS** when `herdr workspace list` no
   longer shows `mission-smoke`, the recorded `comms_pid` is gone, `comms rooms`
   can no longer reach the server, and the committed work survived harvest:
   `git show mission-smoke:smoke-ok.txt` prints `OK`. Clean up the harvest branch:
   `git branch -D mission-smoke`.

## Comms TUI

The `comms tui` dashboard has its own self-contained smoke test (spawns its own
server, no herdr needed): `python3 comms/smoke-tui.py`. It renders live data,
flips CONNECTED -> DISCONNECTED on server loss, recovers, and quits cleanly.
**PASS** on exit 0. Run it after touching `comms/src/tui/`.

If a pane's agent never reaches ready, `herdr pane read <pane> --source recent`
to see why. If the ready-match is wrong, tune `HARNESSES[...]["ready"]` in
`orchestration/spawn.py`. If an agent sits idle after a task is posted, that is
the no-push behavior of comms — `poke` it so it polls `comms inbox`.
