# Smoke test — orchestration harness

Live end-to-end check that a fleet spawns, coordinates over the orbal-net server, and
tears down. Run from an orchestrator pane inside herdr (`HERDR_ENV=1`). Cheap: two
`sonnet` claude agents.

Paste this as the prompt:

---

Run the orchestration smoke test with `orchestration/smoke.roster.json` (feature
`smoke`: `lead-a` + `worker-a-1`, both claude/sonnet). Do each step and report
pass/fail:

1. **Self-check the server.** `orbal-net --selfcheck` prints `orbal-net selfcheck ok`
   (orbal-net is installed via `cargo install orbal-net`; its own repo,
   github.com/zico-io/orbal-net, has its own `cargo test`). **PASS** on exit 0.
2. **Spawn.** `python3 orchestration/spawn.py up orchestration/smoke.roster.json`.
   Expect a printed `{role: pane_id}` map, and `mission.json`
   (`/tmp/botfile-missions/smoke/mission.json`) to carry `orbal_net_url`,
   `orbal_net_token`, `orbal_net_pid` with the server process alive. **PASS** if
   `herdr pane list` shows a `mission-smoke` workspace with a `lead-a` tab and a
   worker split, and the server pid is running.
3. **Point your orbal-net at the server + check in.** Export the coordinates from
   `mission.json`: `export ORBAL_NET_URL=<orbal_net_url> ORBAL_NET_TOKEN=<orbal_net_token>
   ORBAL_NET_AGENT=orchestrator`. Then `orbal-net agents` shows `lead-a` and `worker-a-1`
   registered, and `orbal-net read mission-smoke` shows `lead-a` ready. **PASS** if
   both registered. (`up` already created `mission-smoke` owned by `orchestrator`,
   so you are a member and can `orbal-net send` without a manual `join`.)
4. **Delegate.** `orbal-net send mission-smoke "lead-a: have worker-a-1 write the file
   smoke-ok.txt containing OK and commit it, then confirm."` Agents aren't pushed
   messages, so wake the target: `python3 orchestration/spawn.py poke smoke lead-a`
   (and, if the worker went idle before the task was posted, `... poke smoke
   worker-a-1`). The worker writes+commits inside its isolated mission clone, so
   **PASS** when `smoke-ok.txt` exists at `/tmp/botfile-missions/smoke/work/`
   (`git -C /tmp/botfile-missions/smoke/work log --oneline` shows the worker's
   commit) and the confirmation lands in `squad-lead-a` (`orbal-net read
   squad-lead-a`). Confirm the orchestrator is **not** a member of `squad-lead-a`
   (`orbal-net rooms` — hierarchy holds).
5. **Cross-host transport.** From a second shell with `ORBAL_NET_URL` = the mission's
   advertised IP:port and the same token, `ORBAL_NET_AGENT=probe orbal-net send mission-smoke
   hello`; then `orbal-net read mission-smoke` (as orchestrator) shows it. **PASS** if
   the message lands — proves TCP works off-loopback.
6. **Auth.** `ORBAL_NET_TOKEN=wrong orbal-net rooms` fails (401). **PASS** on nonzero exit.
7. **Layer guard.** `python3 orchestration/spawn.py selfcheck` prints
   `selfcheck ok`. **PASS** on exit 0.
8. **Teardown.** `python3 orchestration/spawn.py down smoke` — kills the orbal-net
   server (all rooms vanish with it), harvests the `mission-smoke` branch back into
   the repo, and closes the workspace. **PASS** when `herdr workspace list` no
   longer shows `mission-smoke`, the recorded `orbal_net_pid` is gone, `orbal-net rooms`
   can no longer reach the server, and the committed work survived harvest:
   `git show mission-smoke:smoke-ok.txt` prints `OK`. Clean up the harvest branch:
   `git branch -D mission-smoke`.

## orbal-net TUI

The `orbal-net tui` dashboard has its own self-contained smoke test (spawns its own
server, no herdr needed) in the orbal-net repo: `python3 smoke-tui.py`. It renders
live data, flips CONNECTED -> DISCONNECTED on server loss, recovers, and quits
cleanly. **PASS** on exit 0. Run it after touching that repo's `src/tui/`.

If a pane's agent never reaches ready, `herdr pane read <pane> --source recent`
to see why. If the ready-match is wrong, tune `HARNESSES[...]["ready"]` in
`orchestration/spawn.py`. If an agent sits idle after a task is posted, that is
the no-push behavior of orbal-net — `poke` it so it polls `orbal-net inbox`.
