# HOST-RUN-PLAYBOOK.md - the real step-4/5 launch, run by the orchestrator on the host

The in-VM coexistence harness proved the bob-as-L1 claims against SIMULATED leads
(see `VERDICT.md`). The REAL host-level launch - bob spawning a LIVE claude/codex/pi
fleet via host herdr + `spawn.py`, and exercising `spawn_bridge_pr` / `spawn_down`
against a real remote under human approval (RFC S9 steps 4-5) - is inherently a
host + human-in-the-loop activity, out of scope for a spawned build VM (mission
non-goal). This is the exact command sequence the orchestrator runs on the host
AFTER this code lands. No em dashes; use "-".

## The shared-server model (what changed, and why)

The host shakedown found that bob's L1 connector holds N mission-room subscriptions
on ONE server (single `ORBAL_NET_URL`), but `spawn.py up` used to start a NEW
per-mission server - so bob could not follow real missions, and a fresh `bin/bob up`
could not boot the connector at all (`ORBAL_NET_URL is not set`). This mission moves
to ONE shared host-level orbal-net server:

- `bin/bob up` starts (or binds to) that ONE persistent `orbal-net serve` and exports
  its `ORBAL_NET_URL`/`ORBAL_NET_TOKEN` (for eve + the connector) plus a dedicated
  `ORBAL_NET_SHARED_URL`/`ORBAL_NET_SHARED_TOKEN` trigger pair.
- With that trigger present, `spawn.py up` CREATES the mission's rooms on the shared
  server and SKIPS starting a per-mission one; `spawn.py down` retires just that
  mission's rooms (`destroy-room`) and leaves the shared server running. With NO
  trigger (a legacy claude-L1 running `spawn.py up` directly), behavior is unchanged -
  a per-mission server exactly as before.
- The shared server OUTLIVES `bin/bob down` (a single bob restart must not drop live
  missions). Tear it down explicitly with `bin/bob server-down`.
- `ORBAL_NET_URL` (eve's in-turn tools + the connector, both host-side) stays
  `127.0.0.1`; `ORBAL_NET_SHARED_URL` (what `spawn.py up` records and hands to mission
  agents) is advertised on the LAN egress IP instead, so a SANDBOX/VM agent can dial the
  host - `orbal-net serve` already binds `0.0.0.0`, only the advertised address changed.
  Override with `ORBAL_NET_ADVERTISE_HOST` for VPN/remote topologies (same var
  `spawn.py`'s own per-mission path already honors).

## Prerequisites (host)

- Node >=24, `eve@0.22.1` resolvable, and on PATH: `herdr`, `orbal-net`, `git`,
  `gh` (authenticated), plus `spawn.py` / `plan_pane.py` under
  `$ORCHESTRATION_DIR` (default `/opt/botfiles/orchestration`).
- A working clone of `zico-io/bob` (this repo, post-merge).
- Vercel access for the AI Gateway token.

## 0. One-time setup

```
cd <bob-clone>
npm ci || npm install                                          # includes the just-bash sandbox backend
vercel link --yes --scope zico-ios-projects --project bob      # writes .env.local (VERCEL_OIDC_TOKEN)
npx eve dev   # ONE TIME per host: installs the microsandbox libkrun runtime to
#               ~/.microsandbox (autoInstall fires only under `eve dev`). `eve start`
#               does NOT auto-install it - skip this and prewarm fails on macOS.
#               Ctrl-C once it is serving; the runtime stays installed.
npx eve build
```

Set the host L1 env. bob now OWNS the shared orbal-net server, so you do NOT set
`ORBAL_NET_URL`/`ORBAL_NET_TOKEN` by hand - `bin/bob up` starts the server and
exports them. Only set the host-identity/orchestration knobs:
```
export BOB_HOST_IDENTITY=<stable host id>      # keys the durable bob:<host> human session
export ORBAL_NET_PORT=<port>                   # OPTIONAL; the shared server's port (default 4100)
export ORCHESTRATION_DIR=<real .botfiles/orchestration path>   # host-exec resolves spawn.py +
#                                              plan_pane.py here; the in-VM default
#                                              /opt/botfiles/orchestration is almost certainly
#                                              NOT the host path - set it.
export HERDR_ENV=1                             # spawn-team precondition; herdr on PATH
# gh must be authenticated (for spawn_bridge_pr); ORBAL_NET_AGENT is forced to
# `orchestrator` by bin/bob (S8 - do not override). Do NOT export ORBAL_NET_SHARED_*
# yourself - bin/bob sets that trigger from the server it starts.
```

## 0b. Pre-flight: run the no-regression proofs (host has KVM + AI Gateway)

These prove the leaf role, durable session, and multi-room semantics still hold.
They could NOT run in the build VM (no `/dev/kvm` for microsandbox, no Vercel token), so
this is where they get their green - run them once here before the live steps:
```
npm run proof:leaf          # leaf worker: one room -> eve turn
npm run proof:durable       # PROOF A: durable bob:<host> session resumes across restart
npm run proof:coexistence   # L1 vs simulated leads: indistinguishability + notify_human +
#                             multi-room attach/detach
npm run proof:shared-server # shared-server model (also passes in-VM; no eve/Vercel needed)
```

The confirm-gate LOGIC (two-phase token: first call = challenge/no side effect, second
call with the exact token = executes, wrong/absent/reused/stale/wrong-action/args-mismatch
token = refused) is validated in-VM by unit tests - no KVM/Gateway needed:
```
npm test                    # includes the confirm-gate + spawn-tools-confirm unit tests
```
Then the REAL-eve acceptance of the gate (it drives a real `eve start` + AI Gateway end to
end and asserts NO `MODEL_CALL_FAILED`) runs here on the host:
```
npm run proof:confirm-gate  # HOST-ONLY: real eve, drives confirm->executes / bad-token->refused,
#                             asserts zero dangling-tool_use (the eve #533 avoidance signal)
```
The minimal `#533` reproducer stays committed as a REGRESSION MARKER (it is NOT an
acceptance gate - it is expected to FAIL today and to start PASSING only once eve fixes the
out-of-band approval-resume, at which point the native `approval: always()` gate can return):
```
npm run repro:eve-533       # HOST-ONLY: reproduces vercel/eve #533; expected-fail today
```

## 1. Launch bob as L1 (RFC S4 - the all-day front end)

```
bin/bob            # starts the shared orbal-net server + eve (:3000, RESUME) +
#                    the L1 connector, then attaches the TUI
# or, non-interactively split:
bin/bob up         # shared server + eve + connector in the background
bin/bob status     # shared-server: up (:4100)  eve: up  connector: up
bin/bob tui        # attach the all-day terminal client to bob:<host>
```

The connector boots even though it drives NO mission yet (zero rooms) - it just
needs the shared server's `ORBAL_NET_URL`, which `bin/bob up` now provides. If
`bin/bob status` shows `shared-server: down`, nothing else will work (a dead shared
server silently breaks every mission) - restart with `bin/bob up`.

The TUI front end (gap #5). `bin/bob tui` launches `client/bob-tui.ts` (the entry
`bin/bob` reads from `BOB_TUI_ENTRY`, defaulted to it). It rides the ONE durable
`bob:<host>` session and renders assistant text / tool cards / `notify_human` relays
(shown as `[mission update]`). The human-in-the-loop gate on the two irreversible
tools (`spawn_bridge_pr`, `spawn_down`) is now CONVERSATIONAL, not a runtime approval
prompt: bob calls the tool once (which returns a confirmation challenge + a one-time
token and does NOT act), relays that challenge as ordinary assistant text, the human
replies with the token as an ordinary message, and bob calls the tool again with the
token to act (step 4). This rides eve's NORMAL turn loop with NO `input.requested`
parking - which is exactly what avoids the eve out-of-band approval-resume bug
(`vercel/eve #533`; see HOST-SHAKEDOWN.md "Approval gate: eve #533 + the conversational
switch"). The runtime-approval answer path (`input.requested` rendering + `inputResponses`)
is kept DORMANT in the client and channel behind a `#533` comment, ready to restore
when eve fixes the out-of-band resume. This is bob's OWN thin channel (`bob.ts` -> eve's
native `send()`), NOT the generic eve channel: the generic channel cannot pin a stable
host-derivable continuation token (it mints a fresh random session id per create), so
it structurally cannot back bob's all-day durable session - see HOST-SHAKEDOWN.md "Why
bob.ts, not the generic eve channel". No upstream durable TUI client exists to inherit
(eve's dev TUI and `@ai-sdk/tui` are both non-durable), so the thin client stays; it
speaks eve's NATIVE session/turn/streaming runtime for everything else.

Durability check (the human-visible property): type a codeword to bob, `bin/bob
down`, `bin/bob up`, `bin/bob tui`, ask bob to recall it - same conversation
resumes (this is PROOF A in production; `bin/bob` never wipes `.workflow-data`).
Note `bin/bob down` stops eve + the connector but LEAVES the shared server up, so
any mission you were driving survives the bob restart; only `bin/bob server-down`
stops the server.

## 2. Scope + spawn a REAL fleet (RFC S9 step 4 in the real)

From the bob TUI (human turn), drive the ported skills - bob asks its interview
questions as ordinary turns and writes the brief/roster via its sandbox:
```
/scope-mission <feature>     # interactive interview -> orchestration/<feature>.brief.md + .roster.json
/spawn-team <feature>        # bob calls spawn_up -> spawn.py up <roster.json> [teams]
```
`spawn_up` shells out to the EXACT `spawn.py up` argv, then calls the connector's
`/control/attach` for `mission-<feature>` (so bob starts receiving that mission's
reports on the live connector without dropping any other mission). Because bob
exported the `ORBAL_NET_SHARED_*` trigger, `spawn.py up` CREATES `mission-<feature>`
on the shared server (no per-mission server is started). A relative `rosterPath`
(e.g. `orchestration/<feature>.roster.json`, what `/scope-mission` writes) resolves
against `.botfiles` (`ORCHESTRATION_DIR`'s parent), not eve's cwd - `spawn_up`
absolutizes it before shelling out, so `spawn.py`'s own cwd never matters. Confirm:
```
orbal-net tui                              # watch the fleet; leads should appear under mission-<feature>
orbal-net peek mission-<feature>           # bob (orchestrator seat) posting the brief/tasks
curl -s 127.0.0.1:3900/control/subscriptions   # mission-<feature> now in bob's subscription set
python3 $ORCHESTRATION_DIR/spawn.py status <feature>   # 'orbal-net server: SHARED <url> (not owned by this mission)'
```

## 3. Verify bob drives the live fleet (indistinguishability, in the real)

- Leads (real claude panes) report into `mission-<feature>`; bob receives each as
  an inbound turn and relays the human-worthy ones into the TUI via `notify_human`.
- bob originates tasks with `orbal_net_send` (as `orchestrator`) - leads cannot
  tell bob apart from a claude L1 (RFC S8).
- Nudge a stalled pane: ask bob to `spawn_poke <feature> <role>` (wraps `spawn.py
  poke`); read a stalled pane via the `herdr_pane_read` tool. HOST-VERIFY (the one
  argv not grounded in real source): confirm `herdr pane read <pane> --source
  recent` matches live `herdr --help` before relying on it in a stall-diagnostic -
  every `spawn.py`/`plan_pane.py` argv is grounded in real source, but this herdr
  verb was taken from `spawn-team.md`'s text without a live herdr to check against.

## 4. Exercise the two irreversible tools via the conversational confirm gate (RFC S9 step 5)

These are the two hard-to-reverse tools. The human-in-the-loop guarantee (RFC S6) is
unchanged - only the MECHANISM moved off eve's broken runtime approval (`vercel/eve
#533`) onto a TOOL-SIDE two-phase conversational confirmation that rides eve's normal
turn loop. The gate is enforced in the tool, not by prompt: the FIRST call performs NO
side effect - it returns a one-time confirmation token (issued server-side, tied to the
exact action + args + this bob session) plus a human-readable challenge; the action runs
ONLY on a SECOND call carrying that exact token, which the tool verifies was issued this
session for this action. A single model call cannot fire the irreversible action; a human
turn supplying the token is structurally required in between. The token is single-use,
per-(action, args), and expires (15 min), so it cannot be reused, replayed, or moved to a
different action or different args.

```
# In the TUI, ask bob to open the PR (this is TWO human turns):
#   Turn 1:  "bridge the PR for <feature>"   -> bob calls spawn_bridge_pr (no confirm_token)
#            -> tool returns { confirmation_required: true, token: "<hex>", challenge: "..." }
#               and does NOT push - bob relays the challenge as ordinary assistant text:
#                 "This will push <feature> and open its PR on zico-io/bob. To confirm,
#                  reply with the token: <hex>"
#   Turn 2:  reply with the token (e.g. "confirm <hex>" or just "<hex>")
#            -> bob calls spawn_bridge_pr AGAIN with confirm_token=<hex>
#            -> tool verifies + consumes the token -> spawn.py bridge-pr <feature> [title]
#               (real push + real PR via gh). The token is now spent (a re-send does nothing).
#   Anything else (no reply / wrong token / a stale token) -> tool returns
#            { confirmed: false, error: "confirmation refused: <reason>" } and does NOT write.
```
Confirm the PR exists on GitHub, and that declining (or replying with a wrong/absent
token) produces NO write. Because there is NO `approval: always()` and NO
`input.requested` parking anywhere in this flow, the eve `#533` dangling-tool_use /
`MODEL_CALL_FAILED` failure cannot occur - the whole exchange is ordinary assistant/human
turns. Then teardown, the same two-turn shape:
```
#   Turn 1:  "tear down <feature>"           -> bob calls spawn_down (no confirm_token)
#            -> returns a confirmation challenge + token; NOTHING is torn down yet
#   Turn 2:  reply with the token
#            -> bob calls spawn_down AGAIN with confirm_token=<hex>
#            -> tool verifies + consumes -> connector /control/detach mission-<feature>
#               (stream closed cleanly while the room is still alive), THEN spawn.py down
#               <feature> (kills panes + RETIRES this mission's rooms on the SHARED server
#               via destroy-room - mission-<feature> as orchestrator + each squad-<lead> as
#               its owning lead - and LEAVES the shared server + every other mission running)
```
Confirm via `orbal-net tui` (and `orbal-net rooms` against the shared server) that
only `mission-<feature>` + its squad rooms went away, the shared server is still up,
and any OTHER concurrent mission bob was driving is untouched (the incremental-detach
+ per-room-teardown property). The shared server is NOT killed by `spawn_down` - only
`bin/bob server-down` stops it.

### Finale run sheet (the live acceptance, end to end)

This is the one continuous run that closes RFC S9 step 5 for real - bob spawns a REAL
SANDBOX fleet, then the human confirms a REAL `spawn_bridge_pr` and a REAL `spawn_down`
through the conversational gate:

1. `bin/bob` up + TUI (steps 1); `bin/bob status` all green.
2. From the TUI: `/scope-mission <feature>` then `/spawn-team <feature>` -> a real fleet
   appears in `orbal-net tui` under `mission-<feature>` (step 2).
3. Let a lead do a small real change and report up; bob relays via `notify_human` (step 3).
4. Ask bob to bridge the PR -> Turn 1 returns the challenge+token (no write); reply with the
   token -> Turn 2 pushes + opens the real PR on `zico-io/bob`. Verify the PR on GitHub.
   Verify a wrong/absent token on a fresh request is refused with no write.
5. Ask bob to tear the mission down -> Turn 1 returns a challenge+token (no teardown); reply
   with the token -> Turn 2 detaches + `spawn.py down`. Verify only that mission's rooms went.
6. Throughout, tail the eve log: it must show ZERO `MODEL_CALL_FAILED` / dangling-tool_use -
   the whole gate is ordinary turns, never an `approval:`-parked resume. That absence IS the
   acceptance signal that this replaces the old (blocked) `approval: always()` finale.

## 5. Full scope-to-teardown cycle (RFC S9 step 6) + cutover (step 7)

Repeat steps 2-4 for a real feature end to end; when satisfied, cut the L1 seat
over from a raw claude pane to `bin/bob` as the standing orchestrator. bob can hold
several `mission-<feature>` sessions at once (N independent 3-layer trees, one L1
identity) - each mission attaches/detaches independently on the one live connector.

## Troubleshooting

- `eve start` fails to prewarm the sandbox on macOS -> the microsandbox libkrun
  runtime is not installed; run `npx eve dev` once (see step 0), Ctrl-C, retry.
  (`npm ls just-bash` is the linux/CI backend check.)
- Model calls 401/expired -> re-run `vercel link` (OIDC token refresh).
- `bin/bob status` shows `shared-server: down` -> every mission is broken; `bin/bob
  up` re-binds it (rooms/messages persist in `.bob-orbal-net.db` across a restart).
- A mission's reports not reaching bob -> `curl 127.0.0.1:3900/control/subscriptions`;
  re-attach with `curl -XPOST 127.0.0.1:3900/control/attach -d '{"room":"mission-<feature>"}'`
  (idempotent; `spawn_up` does this automatically).
- Stale rooms accumulating on the shared server -> harmless (inert sqlite rows). If a
  re-run of the SAME feature/lead hits `room already exists`, either pick a fresh
  feature/lead name or `bin/bob server-down` + `bin/bob up` to start the server clean
  (drops all rooms). Concurrent missions must not reuse a lead role name (their
  `squad-<lead>` rooms would collide on the one shared server).
- `spawn.py up` exits immediately with "BOTFILE_NO_SANDBOX=1 ... does not pre-answer
  claude/codex's first-run prompts" -> bare/local mode (`BOTFILE_NO_SANDBOX=1`) is
  debug-only and unsupported for a real claude/codex fleet (their first-run prompts are
  only pre-answered inside the SANDBOX microVM); this playbook's real run always uses
  SANDBOX (the default), so this only fires if you explicitly set the env var.
