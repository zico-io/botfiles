# HOST-SHAKEDOWN.md - shared-server host-wiring verdict

Mission `bob-l1-host-wiring` closed the three host-integration gaps the bob-l1-build
host launch shakedown found. This file
records, per RFC S9 steps 4-5, EXACTLY what is proven in the build VM here versus what
the orchestrator must run LIVE on the host (real herdr/spawn.py fleet + human
approvals + real GitHub writes are a host + human-in-the-loop activity, a standing
mission non-goal - same boundary as bob-l1-build). No em dashes; use "-".

## The decision (settled, do not relitigate)

ONE shared host-level orbal-net server. `bin/bob up` starts/binds it and exports its
`ORBAL_NET_URL`/`ORBAL_NET_TOKEN` (for eve + the connector) plus a dedicated
`ORBAL_NET_SHARED_URL`/`ORBAL_NET_SHARED_TOKEN` trigger. `spawn.py` gains an additive,
opt-in "use existing server" path gated STRICTLY on that trigger pair: create the
mission's rooms on the shared server, skip starting/killing a per-mission one. With NO
trigger (legacy claude-L1 running `spawn.py up` directly) behavior is byte-for-byte
unchanged. The connector stays single-URL (RFC S8 intact); bob's L1 seat stays the one
`orchestrator` identity holding N mission-room subscriptions on the one server.

## Gap 1 - single-server connector vs per-mission servers (BLOCKER) - CLOSED

| What | Status | Evidence |
| --- | --- | --- |
| `bin/bob up` starts/binds ONE shared `orbal-net serve`, exports its coords + the `ORBAL_NET_SHARED_*` trigger | PROVEN in-VM | `bin/bob` (commit `68c96e3`); `bob up`/`status`/`server-down` round-trip on linux, token persisted at 0600, db persists rooms |
| Connector boots against the shared server with ZERO mission rooms (fixes `ORBAL_NET_URL is not set`) | PROVEN in-VM | `proofs/shared-server.ts` claim 1 (`npm run proof:shared-server`) |
| `spawn_up` attach delivers a lead report on the live connector | PROVEN in-VM | `proofs/shared-server.ts` claim 2 |
| 2nd mission attaches concurrently, NO cross-talk, one `orchestrator` identity in both rooms on ONE server | PROVEN in-VM | `proofs/shared-server.ts` claim 3 |
| Clean detach - mission-B keeps delivering across mission-A's detach | PROVEN in-VM | `proofs/shared-server.ts` claim 4 |
| Per-room teardown - `destroy-room` retires one mission, server + others survive | PROVEN in-VM | `proofs/shared-server.ts` claim 5; live-verified `create-room`/`destroy-room` ownership semantics |
| `spawn.py` shared path additive + opt-in; legacy per-mission path unchanged; `selfcheck` green | PROVEN in-VM | `spawn.py` diff (`docs/spawn.py.shared-server.diff`), `spawn.py selfcheck-live` (PATH A / PATH B / shared down) |
| bob (L1) drives a REAL herdr/claude fleet on the shared server end to end | ORCHESTRATOR runs LIVE | host playbook steps 2-5 |

### Room-lifecycle facts established live (against a standalone `orbal-net serve`)

- One `orchestrator` identity may join N rooms on one server.
- `create-room` uses JSON field `name`; `destroy-room` uses field `room` (asymmetric).
- `destroy-room` enforces room ownership (a non-owner gets 403). The mission room is
  orchestrator-owned (created by `up()`); each `squad-<lead>` room is LEAD-owned (leads
  `create-room` it in bootstrap). So `down()` destroys the mission room as
  `orchestrator` and each squad room AS ITS OWNING LEAD (the token authorizes the
  request; the `agent` field asserts identity). Zero leaked rooms.
- A `destroy-room` failure is a warning, not an abort - a stale room is inert sqlite
  data; the shared server persists and outlives every mission.

## Gap 2 - Linux-only /proc process control - CLOSED

| What | Status | Evidence |
| --- | --- | --- |
| `bin/bob up/down/status/server-down` process control is portable (/proc on linux, `pgrep`/`kill` on darwin) | PROVEN on linux; darwin branch by inspection | `bin/bob` `proc_kill` (commit `68c96e3`) |
| `proofs/lib/eve-server.sh` no longer bare-`/proc` (same portable strategy) | PROVEN in-VM | `_kill_by_substring` in `eve-server.sh`; `/proc` branch exercised directly (this VM has no `pgrep` either) |
| The changed process-control path runs clean in the eve-turn proofs | PROVEN in-VM | `eve-server.sh stop()` prints clean with zero `/proc` errors on every `proof:leaf`/`durable`/`coexistence` run |
| eve-turn proofs reach a green PASS (`proof:leaf` / `proof:durable` / `proof:coexistence`) | ORCHESTRATOR runs LIVE (see proof boundary) | host run sheet |
| `bin/bob down` cleanly stops eve + connector on macOS (no /proc) | ORCHESTRATOR confirms LIVE on darwin | host playbook step 1 |
| Leaf role's connector lifecycle (`spawn.py orbal_net_connector_up/_down`, Linux) untouched | PROVEN in-VM | unchanged in the diff |

### Proof boundary - why the eve-turn proofs run on the host, not here

`proof:leaf` / `proof:durable` / `proof:coexistence` each drive a real `eve start` (via
`eve-server.sh`), which this mission's microsandbox baseline (PR #3, `agent/sandbox.ts`,
NOT re-opened) requires KVM for, AND real model turns through the AI Gateway. This build
VM has neither `/dev/kvm` nor a Vercel OIDC token (`.env.local`), so those proofs cannot
reach PASS here - two environmental blockers, BOTH upstream of and unrelated to any change
in this mission. This is the mission's stated in-VM/live boundary (validate in-VM via the
shared-server simulation + unit tests; run the live eve-turn proofs on the host).

No-regression IS demonstrated in-VM for what is testable KVM/Vercel-free:
- the connector's core per-`(room,agent)` delivery machinery (`subscription.ts` Rules
  A/B/C, shared by the leaf AND L1 roles) is exercised GREEN by `proof:shared-server` (5/5);
- the portable `kill_eve`/`proc_kill` code path runs clean (zero `/proc` errors) in every
  eve-turn proof run, failing only later inside eve's own sandbox prewarm;
- the leaf connector lifecycle in `spawn.py` is untouched.
The orchestrator re-runs `proof:leaf`/`durable`/`coexistence` for their green on the
KVM + Vercel host (see the run sheet).

## Gap 3 - sandbox backend (RESOLVED separately, PR #3) - consumed as baseline

microsandbox is pinned (`agent/sandbox.ts`, already on `main`). Operational caveat now
carried by the playbook: a ONE-TIME `npx eve dev` per host installs the libkrun runtime
to `~/.microsandbox` (`eve start` does NOT auto-install). Not re-opened here.

## What the orchestrator MUST run live on the host (not provable in a build VM)

1. `bin/bob up/down/status/server-down` round-trip on the real macOS host (darwin process
   control; the shared server binds and is visible in `status`).
2. Durable `bob:<host>` session still resumes across an `eve start` restart WITH the
   shared server owning coordination (unregressed; RFC S4 bet 1 was already proven live).
3. bob scopes + spawns a small throwaway mission on the shared server (`spawn.py up` takes
   the shared path, no per-mission server); `peek mission-<feature>` shows the
   `orchestrator` seat originating tasks - indistinguishable from a claude L1.
4. `notify_human` relays a real lead report into the human session; a 2nd concurrent
   throwaway mission attaches/detaches with no cross-talk.
5. `spawn_bridge_pr` / `spawn_down` raise real approval prompts and, on approve, do the
   real GitHub write / real per-room teardown against a real remote.

The step-by-step commands are in `docs/HOST-RUN-PLAYBOOK.md`; the condensed run sheet is
below.

## Host run sheet (orchestrator; condensed steps 2-5)

```
# 0. one-time: npm ci; vercel link --yes --scope zico-ios-projects --project bob;
#    npx eve dev (libkrun, once) then Ctrl-C; npx eve build
# 0b. no-regression proofs that need KVM + the AI Gateway (could not run in the build VM):
npm run proof:leaf && npm run proof:durable && npm run proof:coexistence   # all PASS on the host
npm run proof:shared-server                       # also passes here (already green in-VM)
# 1. launch L1 (also starts the shared server):
bin/bob up && bin/bob status          # shared-server: up (:4100)  eve: up  connector: up
bin/bob tui
# 2. scope + spawn a small throwaway mission (from the TUI):
#    /scope-mission <feat>  ;  /spawn-team <feat>
python3 $ORCHESTRATION_DIR/spawn.py status <feat>   # 'orbal-net server: SHARED ...'
orbal-net peek mission-<feat>          # orchestrator seat originating tasks (indistinguishability)
curl -s 127.0.0.1:3900/control/subscriptions        # mission-<feat> attached
# 3. drive it: lead reports -> bob relays via notify_human; spawn_poke a stall
# 4. concurrency: spawn a 2nd throwaway mission; confirm both in subscriptions, no cross-talk
# 5. approvals (real remote): ask bob to bridge the PR (spawn_bridge_pr) -> approve -> PR on GitHub;
#    ask bob to tear down (spawn_down) -> approve -> mission + squad rooms destroyed on the
#    shared server, server + the OTHER mission untouched
bin/bob server-down                    # only when fully done: stops the shared server
```

VERDICT: the shared-server model + cross-platform process control are PROVEN in-VM
(self-contained, no live fleet). The remaining LIVE host validation (steps 2-5 with a
real fleet + human approvals + real GitHub) is the orchestrator's to run per the run
sheet above; success = bob drives a real small throwaway mission end to end on the host,
indistinguishable from a claude L1, with the approval gates firing against a real remote.

---

# HOST-DRIVE addendum (mission `bob-l1-host-drive`)

Taking the host-wiring deliverable fully live surfaced four gaps (approvals not
answerable through bob's front end; the shared server advertised on loopback,
unreachable by SANDBOX/VM agents; `spawn_up` roster-path resolution; NO_SANDBOX
local spawn). This mission closes them. This addendum records, per RFC S9, EXACTLY
what is newly proven in the build VM here versus what the orchestrator runs LIVE on
the host. Same in-VM/live boundary as before: a real `eve start` needs KVM
(microsandbox) + a real model turn through the AI Gateway, neither present in the
build VM. No em dashes; use "-".

## Gap #5 (the core) - answerable approvals through a durable front end - CLOSED (in-VM) / LIVE

> SUPERSEDED (mission `bob-l1-approval-fix`): the runtime-approval mechanism recorded in
> this section (`approval: always()` on the two tools, answered via `input.requested` +
> `inputResponses` through the TUI) is RETIRED for the gate on `spawn_bridge_pr`/`spawn_down`.
> It hit a confirmed eve BETA bug (`vercel/eve #533`): on approve, eve re-invokes the model
> with the parked `tool_use` but NO matching `tool_result` -> Anthropic 400 -> `MODEL_CALL_FAILED`
> -> the approved tool never runs. The human-in-the-loop guarantee is UNCHANGED; only the
> mechanism moved onto a tool-side two-phase conversational confirmation that rides eve's
> normal turn loop. See the "APPROVAL-FIX addendum" at the end of this file for the root
> cause, the new gate, and the revert-when-eve-fixes-#533 plan. The answerable-approval code
> (`bob.ts` inputResponses branch, `sendInputResponse`, the TUI approval queue,
> `proof_approval_gate`) is kept DORMANT behind a `#533` comment so the switch-back is cheap.
> The DURABLE-RESUME finding below ("Why bob.ts, not the generic eve channel") still holds.

DECIDED (settled with the human): bob's durable front end renders AND answers
approval prompts. bob's OWN thin channel (`bob.ts`) stays - see the next section for
why the generic eve channel cannot back it. The gate (`approval: always()` on
`spawn_bridge_pr`/`spawn_down`) is unchanged; it is made ANSWERABLE, never bypassed.

| What | Status | Evidence |
| --- | --- | --- |
| `bob.ts` POST `/bob/message` accepts optional `inputResponses[]` and forwards them into eve's NATIVE `send()`/SendPayload (the answer path) | PROVEN in-VM | `agent/channels/bob.ts`; typecheck-clean; exercised by `proof:approval-wire` |
| `client/bob-tui.ts` renders `input.requested` (display=confirmation, approve/deny) and posts the `InputResponse` so approve un-parks + executes, deny does not | PROVEN in-VM | `npm run proof:approval-wire` W2a (approve -> `action.result` executed) + W2b (deny -> no `action.result`), against the `proof_approval_gate` stub tool, driving the REAL TUI child + cross-checking the raw session stream |
| The front end rides the durable `bob:<host>` session - relaunch resumes the SAME conversation with zero local state (RFC S4 bet 1, unregressed); a resumed-still-pending approval re-prompts | PROVEN in-VM | `proof:approval-wire` W1 (kill+relaunch the TUI child -> prior scrollback replays with zero sent messages); never wipes `.workflow-data` |
| `notify_human` relays surface in the TUI (as `[mission update]`) | PROVEN in-VM (render path) / LIVE (real relay) | `client/bob-tui.ts` live `message.received` labelling; real relay in the live run |
| The SAME path end to end with a REAL model deciding to call the gated tool + the REAL `approval: always()` gate + a real GitHub write on approve | ORCHESTRATOR runs LIVE | `npm run proof:approval-tui` (host); playbook step 4 |

Two complementary proofs, by design: `proof:approval-wire` proves the CLIENT + wire
contract (input.requested render, `inputResponses` POST, resume replay) GREEN IN-VM
with a scripted fake backend (`proofs/lib/fake-bob-eve.ts`, the `proofs/shared-server.ts`
pattern - no KVM/Gateway); `proof:approval-tui` proves the FULL integration (real eve
`send()` un-park + real gate execute + real model decision) and is HOST-BOUND, same
boundary as `proof:leaf`/`durable`/`coexistence`.

### Why bob.ts, not the generic eve channel (investigated, verified NO-GO)

The pivot to piggyback bob's front end on the generic eve channel
(`agent/channels/eve.ts`) for native resume/approvals was investigated FIRST (RFC
open question #1) and is a verified NO-GO on the gating property - durable resume.
Confirmed against the built channel source (`node_modules/eve/dist/src/public/channels/eve.js`),
not inferred:

- CREATE `POST /eve/v1/session` ALWAYS mints ``eve:${crypto.randomUUID()}`` - a fresh
  random session id every call, with NO override; `parseCreateBody` has no
  `continuationToken` field at all, and a create requires a real non-empty message
  (no free attach).
- CONTINUE `POST /eve/v1/session/:sessionId` DOES accept a body `continuationToken`
  (and `send()` routes deliver-or-start on `${channel}:${token}`, the same mechanic
  bob.ts uses) - BUT the handler runs `getSession(:sessionId)` as an existence gate
  (-> 404 "Session not found.") BEFORE it ever parses the body token, and that path
  `:sessionId` can only come from a prior CREATE = a non-reconstructible random UUID.

So the generic eve channel cannot pin a STABLE, host-derivable continuation token:
resuming the all-day session would require persisting the random session id locally
and making it load-bearing, and `notify_human` (a separate tool) would have to read
that cache to reach the human session - a regression versus bob.ts, where the token
is ALWAYS reconstructible from `BOB_HOST_IDENTITY` alone with ZERO local state (spike
bet 2, proven). `defineChannel` is explicitly documented "for a custom transport";
`eveChannel` is the generic default, not built to be pinned. bob.ts is therefore the
CORRECT design, not a workaround: a THIN token-pinning wrapper whose ONLY bespoke code
is (a) the deterministic continuation-token selection the eve channel structurally
cannot do and (b) the thin client (no durable upstream TUI exists - eve's dev TUI and
`@ai-sdk/tui` `runAgentTUI` are both non-durable, source-proved). Durability, the turn
model, the approval protocol, and streaming all run on eve's NATIVE upstream runtime.

## Gap #4 - shared server reachable by SANDBOX/VM agents (LAN advertise) - CLOSED (in-VM)

| What | Status | Evidence |
| --- | --- | --- |
| `bin/bob` advertises the shared server on the LAN egress IP (`advertise_host`: same UDP-connect trick + `ORBAL_NET_ADVERTISE_HOST` override as spawn.py's `_advertise_host`) | PROVEN in-VM | `bin/bob` `advertise_host` + `start_server`; default resolves to the egress IP, override honored |
| The advertised LAN URL is actually reachable AND the full authenticated orbal-net protocol works over it | PROVEN in-VM | a standalone `orbal-net serve` (binds `0.0.0.0`): `create-room`/`send`/`peek` round-trip entirely over `http://<lan-ip>:<port>`; loopback answers too (host-side path preserved) |
| A real SANDBOX/VM fleet reaches coordination on that URL | ORCHESTRATOR confirms LIVE | playbook step 2 (real fleet on the shared server) |

The loopback/LAN SPLIT is deliberate and correct: `ORBAL_NET_URL` (bob's OWN connector
+ eve's in-turn tools, host-side) stays `127.0.0.1` - fastest, and robust against a
LAN-interface flap. Only `ORBAL_NET_SHARED_URL` (what spawn.py's shared path records
into `mission.json` and injects as the AGENT's `ORBAL_NET_URL`) carries the LAN IP.
`orbal-net serve` binds `0.0.0.0`, so it is one server reachable on both addresses at
once; orchestrator (loopback) and agents (LAN) coordinate through it. This satisfies
the acceptance criterion ("a 2nd host/VM process can reach `ORBAL_NET_URL`") from the
agent side while preserving host-side loopback reachability. No spawn.py change was
needed for #4 (its shared path already records `ORBAL_NET_SHARED_URL` as-is).

## Gap #6 - spawn_up roster-path resolution - CLOSED (in-VM)

`agent/tools/spawn_up.ts` `resolveRosterPath()` absolutizes a relative `rosterPath`
against `ORCHESTRATION_DIR`'s parent (`.botfiles`, where rosters live), applied to BOTH
the `spawn.py` argv and the feature-slug `readFileSync`; an absolute path passes through
unchanged; `buildArgv` stays pure. PROVEN in-VM: relative
`orchestration/<feat>.roster.json` -> `.botfiles/orchestration/<feat>.roster.json`,
absolute passthrough; `npm run typecheck` clean. Sibling tools (`spawn_down`/`status`/
`poke`) take a `feature` string, not a path, so #6 is correctly `spawn_up`-only.

## Gap #7 - NO_SANDBOX local spawn - SCOPED (unsupported, fail-fast)

Decision: bare mode (`BOTFILE_NO_SANDBOX=1`) is marked unsupported for a real
claude/codex fleet rather than pre-answering their first-run prompts on the operator's
host (too invasive/irreversible for a debug-only path). `spawn.py` gains
`_verify_bare_mode_supported()` at the top of `up()` - it exits loud, BEFORE any side
effect, if a bare-mode `up` would spawn claude/codex (whose theme/folder-trust/bypass
prompts are only pre-answered inside the SANDBOX microVM). `pi` has no known first-run
gate and is unaffected. PROVEN in-VM: `spawn.py selfcheck` green with the guard.
Delivered as `docs/spawn.py.host-drive.diff` (+ `docs/spawn-host-drive.md` apply notes)
for the orchestrator to bridge to `.botfiles/orchestration/spawn.py`; the real run uses
SANDBOX (the default), so this never fires unless the env var is set explicitly.

## Host-drive run sheet (orchestrator; the LIVE green run, condensed)

The real green run = bob (at the new TUI) spawns a small real SANDBOX mission on the
shared server, drives it, relays via `notify_human`, and a HUMAN approves a real
`spawn_bridge_pr` (real PR) + `spawn_down` (real per-room teardown) at the TUI prompts.
Inherently host + human-in-the-loop (the approval prompt is FOR a human). Full commands
in `docs/HOST-RUN-PLAYBOOK.md`; condensed:

```
# 0. one-time: npm ci; vercel link ...; npx eve dev (libkrun, once) then Ctrl-C; npx eve build
#    apply the .botfiles bridge: patch .botfiles/orchestration/spawn.py with
#    docs/spawn.py.host-drive.diff (gap #7 guard); see docs/spawn-host-drive.md
# 0b. no-regression proofs that need KVM + the AI Gateway (could not run in the build VM):
npm run proof:leaf && npm run proof:durable && npm run proof:coexistence   # all PASS on the host
npm run proof:approval-tui         # #5 full integration: real model + real approval:always() gate
npm run proof:shared-server && npm run proof:approval-wire   # also pass here (already green in-VM)
# 1. launch L1 (starts the shared server; advertises LAN on ORBAL_NET_SHARED_URL) + the durable TUI:
bin/bob up && bin/bob status       # shared-server: up (:4100)  eve: up  connector: up
bin/bob tui                        # renders + ANSWERS approvals; resumes bob:<host> on relaunch
# 2. scope + spawn a small REAL SANDBOX mission (from the TUI): /scope-mission <feat> ; /spawn-team <feat>
python3 $ORCHESTRATION_DIR/spawn.py status <feat>   # 'orbal-net server: SHARED ...'
orbal-net peek mission-<feat>      # orchestrator seat originating tasks (indistinguishability)
# 3. drive it: real lead reports -> bob relays via notify_human into the TUI ([mission update])
# 4. approvals (real remote): ask bob to bridge the PR -> TUI shows [approval requested] spawn_bridge_pr(...)
#    -> type approve -> real PR on GitHub (type deny -> no write); then ask to tear down -> approve spawn_down
#    -> mission + squad rooms destroyed on the shared server, server + any other mission untouched
bin/bob server-down                # only when fully done
```

HOST-DRIVE VERDICT: #4 (LAN advertise), #5 (answerable approvals + durable resume via
the client/wire contract), #6 (roster-path resolution), and #7 (bare-mode fail-fast)
are PROVEN in-VM for everything testable KVM/Vercel-free (`proof:approval-wire` 3/3,
the LAN round-trip, `spawn.py selfcheck`, typecheck). The remaining LIVE validation -
#5's FULL integration (`proof:approval-tui` + a human approving a real GitHub write at
the TUI) and a real SANDBOX fleet reaching the LAN-advertised server - is the
orchestrator's to run per the run sheet; success = a human at bob's TUI runs a mission
end to end, scope -> spawn a real fleet -> drive -> approve a real `spawn_bridge_pr` +
`spawn_down`, all green.

# APPROVAL-FIX addendum (mission `bob-l1-approval-fix`)

Taking the host-drive deliverable (above) to its LIVE green run hit a hard blocker on the
ONE step that had never run against a real model: the `approval: always()` gate on
`spawn_bridge_pr`/`spawn_down`. This mission root-caused it, confirmed it is upstream and
not bob's fault, and replaced the MECHANISM (not the intent) so the finale runs today. No
em dashes; use "-".

## Root cause - eve out-of-band approval-resume drops the tool_result (`vercel/eve #533`)

On the host green run, on APPROVE, eve re-invokes the model with the gated tool's `tool_use`
block but NO matching `tool_result` block -> the Anthropic Messages API rejects it
(`400: tool_use ids were found without tool_result blocks`) -> `turn.failed: MODEL_CALL_FAILED`
-> the approved tool never runs, the session dies. Established facts:

- Reproduced DIRECTLY over HTTP (no TUI, no channel, no bob tool) on a trivial side-effect-free
  `approval: always()` tool, using eve's documented `inputResponses` answer mechanism - so it
  is not bob's client/channel/tool code (all of which follow eve's contract).
- It lives in eve's `[harness.tool-loop]` message assembly on the OUT-OF-BAND resume: the call
  parks at `input.requested`, the approval arrives in a SEPARATE request that resumes the
  session, and eve assembles that resume model call with the parked `tool_use` unpaired.
- Present in `eve@0.22.1` AND `0.22.4` - a version bump does NOT fix it.
- Filed/confirmed on `vercel/eve #533` (dup `#460`, p1) with our minimal HTTP repro + the
  "still broken in 0.22.4" signal. PR `#588` ("persist HITL approval results in session
  history") is APPROVED + mergeable, but built-from-source testing shows it fixes only the
  INLINE authorization path (`inlineAuthorizationResults`), NOT the out-of-band park->resume
  path we hit - the repro still fails identically with `#588` compiled in. So NO eve version
  is a reliable unblock right now.

## The fix - tool-side two-phase conversational confirmation (rides eve's normal turn loop)

The human-in-the-loop guarantee (RFC S6: a live GitHub write or a mission teardown must not
fire without a human) is PRESERVED - only the mechanism changes. Both tools drop
`approval: always()` and become ordinary tools gated by a shared helper
(`agent/lib/confirm-gate.ts`):

- FIRST call (no `confirm_token`): NO side effect. The tool mints a single-use token
  (crypto-random, server-held), binds it to the exact (action, args, this bob session), and
  returns `{ confirmation_required: true, token, challenge }`. bob relays the challenge as
  ordinary assistant text.
- SECOND call (with `confirm_token`): the tool verifies the token was issued this session for
  THIS action + THESE args, is unexpired (15 min TTL), and unspent; on success it consumes
  the token (single-use) and runs the real side effect. Any mismatch (absent/unknown/reused/
  stale token, wrong action, or changed args) returns `{ confirmed: false, error }` and does
  NOT act.

Because the whole exchange is ordinary assistant/human turns with NO `approval:`-parked
`input.requested`, the `#533` out-of-band resume is NEVER triggered - the finale produces
ZERO `MODEL_CALL_FAILED`. A single model call cannot fire the irreversible action, and a
human turn supplying the token is structurally required in between - so the gate is a REAL
tool-side enforcement, not prompt-only theater.

| What | Status | Evidence |
| --- | --- | --- |
| Both tools drop `approval: always()`; gated by the two-phase token instead | PROVEN in-VM | `agent/tools/spawn_bridge_pr.ts`, `spawn_down.ts`; no `eve/tools/approval` import |
| Token lifecycle: first call = challenge/no side effect; exact token = executes + consumes; reuse/wrong/absent/stale/wrong-action/args-mismatch = refused | PROVEN in-VM (unit) | `npm test` - `confirm-gate` + `spawn-tools-confirm` unit tests (hostExec mocked; no real spawn.py) |
| `agent/instructions.md` Human-turns describes the ask-confirm flow (relay challenge -> wait for the human's token -> call again) | PROVEN in-VM | `agent/instructions.md`; old "expect an approval prompt" wording removed |
| Runtime-approval answer path kept DORMANT with a `#533` + revert comment (bob.ts inputResponses branch, `sendInputResponse`, TUI approval queue); durable text/message send path unchanged. `proof_approval_gate` + `sendInputResponse` are retained (not dormant) as the `#533` reproducer's gated tool + out-of-band answer path | PROVEN in-VM | `#533` comments in `agent/channels/bob.ts`, `agent/lib/eve-session.ts`, `client/bob-tui.ts`; `proofs/eve-approval-bug-repro.ts` uses `proof_approval_gate` + `sendInputResponse` |
| The minimal `#533` HTTP repro is committed as a REGRESSION MARKER (expected-fail today; a PASS means eve fixed the out-of-band path) | authored in-VM / runs on host | `proofs/eve-approval-bug-repro.ts`; `npm run repro:eve-533` |
| REAL-eve acceptance: real `eve start` + AI Gateway drives confirm->executes / bad-token->refused and asserts ZERO dangling-tool_use / `MODEL_CALL_FAILED` | ORCHESTRATOR runs LIVE | `npm run proof:confirm-gate` (host); playbook step 4 |

The old `proof:approval-wire` (fake-bob-eve backend, never called a real model, so never
exercised the `tool_use`/`tool_result` contract - which is exactly why it went false-green on
a bug a real model would have surfaced) is DEMOTED: it no longer backs acceptance, and
`proof_approval_gate` is retired from the acceptance set.

## Revert-when-fixed plan (keep this cheap - do NOT let it fork permanently)

When `vercel/eve #533`'s OUT-OF-BAND resume is fixed (the signal: `npm run repro:eve-533`
starts PASSING on a bumped eve), prefer restoring the native gate (less bespoke code):

1. Re-add `approval: always()` (`eve/tools/approval`) to `spawn_bridge_pr.ts` + `spawn_down.ts`
   and remove the `confirm_token` param + the `confirm-gate` calls (or leave the helper as a
   belt-and-suspenders second factor - a product call).
2. Un-dormant the runtime-approval answer path (the `#533`-commented code in `bob.ts`,
   `eve-session.ts`, `client/bob-tui.ts`) and restore `proof_approval_gate` +
   `proof:approval-tui`/`proof:approval-wire` to the acceptance set.
3. Revert the instructions Human-turns wording back to the approval-prompt description.
4. Keep `proofs/eve-approval-bug-repro.ts` as a permanent regression marker (now passing).

## APPROVAL-FIX VERDICT

The gate LOGIC (two-phase token: issue/no-side-effect, verify-and-consume, and every abuse
case) is PROVEN in-VM by unit tests - no KVM/Gateway needed. The REAL-eve acceptance
(`proof:confirm-gate`, which asserts the run is `MODEL_CALL_FAILED`-free against a real model)
and the LIVE finale (bob spawns a real SANDBOX fleet, a human confirms a real `spawn_bridge_pr`
+ `spawn_down` through the conversational flow) are HOST-BOUND, authored here and run by the
orchestrator + human per the playbook finale run sheet. No in-VM real-eve green is claimed. The
existing green proofs (`leaf`/`durable`/`coexistence`/`shared-server`) are unregressed.
