# Mission brief: bob-l1-host-wiring

Long name: "close the host-integration gaps found in the bob-l1-build host launch shakedown so bob-as-L1 can actually drive live missions on the host (RFC S9 steps 4-5 unblocked): reconcile bob's single-server L1 connector with spawn.py's per-mission servers by moving to ONE shared host-level orbal-net server, fix the Linux-only /proc process control in bin/bob + the proof scripts for macOS, then re-run the real host playbook steps 2-5 to validate"

## Goal
The bob-l1-build mission built the dual-role L1 harness and proved it in-VM against
SIMULATED leads; the host launch shakedown then proved RFC S4 bet 1 (durable bob:<host>
session resume) LIVE on the host, but hit three real host-integration gaps the in-VM proof
could not surface. This mission closes them so bob-as-L1 can drive a REAL fleet on the host:
1. (BLOCKER) bob's L1 connector uses ONE orbal-net server for all mission rooms (single
   ORBAL_NET_URL; `/control/attach` takes only a room name), but `spawn.py` provisions a
   NEW per-mission server (own URL/token). So bob cannot follow real missions. RESOLUTION
   (decided): move to ONE shared host-level orbal-net server - bob starts/binds it at L1
   launch, and `spawn_up` creates each mission's rooms on THAT server instead of spawning a
   new one. The connector stays single-URL (RFC S8 design intact). This ALSO fixes the
   connector's fresh-launch boot (it now has a real ORBAL_NET_URL - bob's own server).
2. `bin/bob` (up/down/status) and the proof scripts use `/proc` for process control, which
   is Linux-only; on the macOS host `bob down` cannot kill. Make process control
   cross-platform (darwin + linux).
3. With 1+2 fixed, RE-RUN the real host playbook steps 2-5 (bob scopes+spawns a live fleet,
   drives it, notify_human relays, multi-room attach/detach across two concurrent real
   missions, approval-gated bridge/teardown fire real prompts) and produce a host-shakedown
   VERDICT. Success = bob drives a real (small, throwaway) mission end to end on the host,
   indistinguishable from a claude L1, with the approval gates working against a real remote.

## In scope
Two repos. PRIMARY is `/Users/percules/dev/bob` (the mission clone). `spawn.py` +
`AGENTS.md` live in the orchestrator's `.botfiles` repo, NOT in the bob clone - changes to
them are PREPARED as a diff/patch for the orchestrator to apply and commit to `.botfiles`
(seeded into the clone at `docs/reference/` for grounding).

- Shared-server model (gap #1, the core):
  - `bin/bob up` starts (or binds to an already-running) ONE persistent host-level orbal-net
    server at L1 launch, and exports its `ORBAL_NET_URL`/`ORBAL_NET_TOKEN` for bob's
    connector. `bin/bob down` stops bob (eve + connector) but does NOT kill the shared server
    unless explicitly asked (it outlives a single bob restart; a separate `bin/bob
    server-down` or documented teardown is fine). The connector boots with zero mission rooms
    against this server (no hard ORBAL_NET_URL-at-boot failure).
  - `spawn.py` gains an ADDITIVE "use existing server" path (prepared as a diff for
    `.botfiles`): when a shared server URL/token is provided (bob sets it via env, e.g.
    `ORBAL_NET_URL`/`ORBAL_NET_TOKEN` already exported), `up` CREATES the mission's rooms on
    that server and SKIPS starting a new per-mission server; `down` removes/leaves the
    mission's rooms and SKIPS killing the shared server. When NO shared server is provided
    (a legacy claude L1 running `spawn.py up` directly), behavior is UNCHANGED - a per-mission
    server as today. This is the load-bearing constraint: the claude-L1 path must not regress.
  - bob's `spawn_up`/`spawn_down` tools (bob repo) attach/detach the mission subscription on
    the live connector after `up`/before `down`, exactly as built - now pointing at the shared
    server. The single `orchestrator` identity holds N mission-room subscriptions on the one
    server (RFC S8).
- Cross-platform process control (gap #2): `bin/bob` up/down/status and the proof runner
  helpers (`proofs/lib/eve-server.sh` and any /proc use) work on darwin AND linux (e.g.
  `lsof`/`pgrep`/`kill` on darwin, `/proc` on linux, or a portable shared helper). `bin/bob
  down` cleanly stops eve + connector on macOS. Leaf role launch (spawn.py's eve harness in
  the VM) is unaffected.
- Host validation (gap #3): update `docs/HOST-RUN-PLAYBOOK.md` for the shared-server flow,
  and provide a crisp, reproducible host script/checklist for the orchestrator to run steps
  2-5 on the host: bob (L1) scopes+spawns one small throwaway mission on the shared server,
  drives a lead indistinguishably (peek shows `orchestrator` originating tasks), notify_human
  relays a real lead report into the human session, a 2nd concurrent throwaway mission
  attaches/detaches with no cross-talk, and `spawn_bridge_pr`/`spawn_down` raise real approval
  prompts. As much as can be validated in-VM (a shared-server simulation + unit tests) is;
  the LIVE host run is executed by the orchestrator afterward (see Non-goals).

## Non-goals
- The LIVE host run of steps 2-5 (bob spawning a real herdr/claude fleet, real GitHub writes
  under approval) is executed by the ORCHESTRATOR on the host after this code lands - it needs
  host herdr/spawn.py + human-in-the-loop approvals, out of scope for a spawned build VM
  (same boundary as bob-l1-build). In-VM: validate via a shared-server simulation + argv/unit
  tests; deliver the host script for the orchestrator to run.
- Do NOT change spawn.py's per-mission-server behavior for the legacy claude-L1 path - the
  shared-server mode is strictly ADDITIVE and opt-in (triggered by a preset shared server).
- No remote/Vercel-deployed orchestrator. Local-first, one host, one shared server.
- Do not regress the leaf role, the durable bob:<host> session (proven on the host), the
  native-channel wire contract, the connector's exactly-once/cursor/park-gate, the approval
  gating, or the coding-tools feature - all reused/extended additively.
- Do not re-open the sandbox-backend fix (shipped separately, PR #3) - consume it as baseline.
- No entity or memory-fact writing.

## Constraints
- Ground on and reuse: the bob-orchestrator RFC (S5/S8 native-channel + connector + membership),
  the bob-l1-build deliverable (already on `main`: `bin/bob`, `connector/` with
  Subscription/Manager/control server, the `spawn_*` tools, `docs/L1-DESIGN.md`,
  `docs/HOST-RUN-PLAYBOOK.md`, `VERDICT.md`), and the shakedown findings (seeded at
  `docs/reference/shakedown-findings.md`). Reuse the connector's per-`(room,agent)` machinery;
  this is additive wiring, not a redesign.
- eve baseline: `eve@0.22.1`, Node >=24, `agent/sandbox.ts` pins microsandbox (PR #3) - which
  needs a ONE-TIME libkrun runtime install per host (`npx eve dev` once installs it to
  `~/.microsandbox`; `eve start` does NOT auto-install). The updated host playbook must
  include this runtime-install step. AI Gateway via `vercel link --yes --scope
  zico-ios-projects --project bob`. `eve start` RESUMES durable sessions; never wipe
  `.workflow-data` in bob's launch path.
- `orbal-net`'s existing CLI/server is consumed as-is (the shared server is just a long-lived
  `orbal-net serve`); do not change the orbal-net wire protocol. Room-membership enforcement
  stays in the server. bob's L1 seat stays the `orchestrator` identity (S8).
- No em dashes; use "-". Consistent vocabulary (herdr, orbal-net serve/recv/peek/send/event,
  continuation token, session/turn, mission-<feature>/squad-<lead>, orchestrator seat).
- Two-repo delivery: bob changes committed to the mission branch (orchestrator bridges the PR
  to `zico-io/bob`); the `spawn.py` (+ any `AGENTS.md`) change prepared as a diff/patch file in
  the bob clone for the orchestrator to apply + commit to `.botfiles`. Agents have no
  gh/network; prepare artifacts, the orchestrator executes every live git/GitHub step.

## Acceptance criteria
- `bin/bob up` on a fresh host: starts/binds ONE shared orbal-net server, brings up eve + the
  L1 connector (connector boots with zero rooms, no ORBAL_NET_URL error), and the durable
  bob:<host> session still resumes across restart (unregressed). `bin/bob down` cleanly stops
  eve + connector on macOS (no /proc).
- A prepared `spawn.py` diff (against the seeded current spawn.py) that adds the opt-in
  "use existing server" path: `up` creates rooms on the shared server + skips server start;
  `down` skips server kill; NO shared server -> per-mission behavior byte-for-byte unchanged.
  Includes a test/demo proving both paths (shared vs per-mission).
- An in-VM shared-server validation: bob (L1) + a simulated lead on the shared server, a
  mission attached via `spawn_up`'s path, a 2nd mission attached concurrently (no cross-talk),
  one detached cleanly - all on the ONE shared server. PASS/FAIL output.
- Cross-platform process control verified on the host (darwin) - `bin/bob up/down/status`
  round-trips cleanly - and unregressed on linux (the VM proofs still pass).
- `docs/HOST-RUN-PLAYBOOK.md` updated for the shared-server flow + a step-2-5 host checklist
  the orchestrator runs. A `HOST-SHAKEDOWN.md` (or VERDICT update) recording what is proven
  in-VM vs what the orchestrator must run live.
- No regression: leaf role, durable session, approval gating, coding tools all still pass
  their proofs (`proof:leaf`, `proof:durable`, `proof:coexistence`). No em dashes.

## Affected areas
- `/Users/percules/dev/bob` (mission clone): `bin/bob` (shared-server launch + darwin process
  control), `connector/` (no-room boot against the shared server; the attach path already
  exists), possibly `agent/tools/spawn_up.ts`/`spawn_down.ts` (pass/inherit the shared-server
  env), `proofs/lib/*` (portable process control) + a shared-server proof, `docs/HOST-RUN-
  PLAYBOOK.md`, `HOST-SHAKEDOWN.md`.
- Prepared for `.botfiles` (orchestrator-applied): `spawn.py` "use existing server" diff, and
  a one-line `AGENTS.md` note if the orchestration protocol needs it.
- Seeded reference (orchestrator adds to the clone; remove before final): current
  `orchestration/spawn.py`, `AGENTS.md`, `.botfile/memory/tools/orchestration.md`, the RFC,
  and `shakedown-findings.md`.

## Risks and unknowns
- spawn.py "use existing server" must be truly additive - the legacy claude-L1 per-mission
  path is load-bearing and in daily use; a regression there breaks every current mission.
  Gate the shared path behind an explicit preset (shared server env present) and prove the
  per-mission path unchanged.
- Room lifecycle on a shared server: with one long-lived server, `down` must remove/retire a
  mission's rooms WITHOUT killing the server or other missions' rooms. Confirm orbal-net
  supports per-room teardown (or that leaving stale rooms is harmless); today `down` kills the
  whole server. This is the trickiest correctness point.
- Server ownership/liveness: who owns the shared server's lifecycle (bob's `bin/bob`? a
  separate host daemon?), and how `status` surfaces it. A dead shared server silently breaks
  all of bob's missions - liveness must be visible.
- Identity/token: bob's connector holds N subscriptions under one `orchestrator` identity on
  the shared server - confirm the server accepts one identity joined to N rooms (it did in-VM
  with the mission's own server; re-confirm on a standalone shared server).
- Cross-platform process control must not break the leaf role's connector lifecycle in the VM
  (spawn.py's `orbal_net_connector_up`/`_down`, which are Linux) - keep those paths working.
- Two workers on shared files (bin/bob) can collide: the lead fixes bin/bob's shape/ownership
  first; worker-server owns the server+spawn.py-diff, worker-portability owns process control -
  coordinate the bin/bob edits through the lead.

## Team plan
- repo: `/Users/percules/dev/bob`
- **host-lead** (claude/opus): owns the shared-server reconciliation design and integration,
  the `bin/bob` shared-server launch shape, the in-VM shared-server validation, the `spawn.py`
  diff review + the `.botfiles` prep, the updated host playbook + `HOST-SHAKEDOWN.md`, and the
  step-2-5 host checklist for the orchestrator. Fixes bin/bob's shape before workers diverge;
  relays the two-repo bridge asks.
  - **worker-server** (claude/sonnet): the shared-server model - `bin/bob` starts/binds one
    persistent orbal-net server + exports its URL/token to the connector; the connector boots
    with zero rooms against it; and the ADDITIVE `spawn.py` "use existing server" diff (up
    creates rooms on the shared server + skips server start; down skips server kill; no-shared-
    server path unchanged) with a test proving both paths. Confirms per-room teardown +
    one-identity-N-rooms on a standalone server.
  - **worker-portability** (claude/sonnet): cross-platform process control - `bin/bob`
    up/down/status and `proofs/lib/*` work on darwin AND linux (no bare `/proc`); `bin/bob
    down` cleanly stops eve + connector on macOS; the VM proofs (`proof:leaf`/`durable`/
    `coexistence`) still pass unregressed. Refreshes any launch/teardown docs touched.
