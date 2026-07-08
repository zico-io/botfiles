# Smoke test — orchestration harness

Live end-to-end check that a fleet spawns, registers, coordinates, and tears
down. Run from an orchestrator pane inside herdr (`HERDR_ENV=1`). Cheap: two
`sonnet` claude agents.

Paste this as the prompt:

---

Run the orchestration smoke test with `orchestration/smoke.roster.json` (feature
`smoke`: `lead-a` + `worker-a-1`, both claude/sonnet). Do each step and report
pass/fail:

1. **Register + room.** agent-comms: `register` as `orchestrator`, `create_room`
   `mission-smoke` (public).
2. **Spawn.** `python3 orchestration/spawn.py up orchestration/smoke.roster.json`.
   Expect a printed `{role: pane_id}` map. **PASS** if `herdr pane list` shows a
   `mission-smoke` workspace with a `lead-a` tab and a worker split.
3. **Check-in.** `list_agents` shows `lead-a` and `worker-a-1` registered;
   `read_room mission-smoke` shows `lead-a` ready. **PASS** if both registered.
4. **Delegate.** Post to `mission-smoke`: "lead-a: have worker-a-1 write the file
   `smoke-ok.txt` containing OK, then confirm." **PASS** when `smoke-ok.txt`
   exists in the repo and the confirmation lands in `squad-lead-a`. Confirm the
   orchestrator is **not** a member of `squad-lead-a` (hierarchy holds).
5. **Layer guard.** `python3 orchestration/spawn.py selfcheck` prints
   `selfcheck ok`. **PASS** on exit 0.
6. **Teardown.** `python3 orchestration/spawn.py down smoke`, then agent-comms
   `destroy_room mission-smoke` and `destroy_room squad-lead-a`. **PASS** when
   `herdr workspace list` and `list_rooms` no longer show them. Delete
   `smoke-ok.txt`.

If a pane's agent never reaches ready, `herdr pane read <pane> --source recent`
to see why. If the ready-match is wrong, tune `HARNESSES[...]["ready"]` in
`orchestration/spawn.py`.
