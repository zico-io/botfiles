# Mission brief: bob-l1-build

Long name: "build the real bob orchestrator per the bob-orchestrator RFC S9 steps 4+ - promote bob from a proven eve leaf worker to the production L1 orchestration harness a human launches via CLI and interacts with all day, driving missions over orbal-net as a native channel; extend the existing zico-io/bob harness to be dual-role (leaf OR L1); prove it with an in-VM coexistence harness against simulated leads; the real host-level launch + bridge/teardown validation is run by the orchestrator after the code lands"

## Goal
Turn the bob-orchestrator RFC (proven-out design) and the bob-l1-spike (both new bets GO)
into the PRODUCTION bob L1 orchestration harness, built into the existing `zico-io/bob`
repo alongside the proven leaf role so ONE `bob` harness can run as either a leaf worker or
the L1 orchestrator. Success = a bob you can launch via CLI that (a) holds an all-day
durable human session, (b) drives N concurrent `mission-<feature>` rooms as a native eve
channel indistinguishably from today's claude L1, (c) exposes the orchestration surface
(spawn.py / herdr / GitHub-bridge as typed tools, hard-to-reverse ones approval-gated) and
the ported `/scope-mission` + `/spawn-team` skills - PROVEN by a repeatable in-VM
coexistence harness (bob-as-L1 against SIMULATED leads on a throwaway orbal-net room) with a
GO/NO-GO VERDICT. The real host-level launch (bob spawning a live claude fleet via host
herdr/spawn.py) and the bridge/teardown-under-approval validation (RFC S9 steps 4-5 in the
real) are run by the ORCHESTRATOR on the host after this code lands - they are inherently
host/human activities, out of scope for a spawned build VM (see Non-goals).

## In scope
Build, into `/Users/percules/dev/bob`, extending (not replacing) the leaf role. Reuse the
proven leaf `agent/channels/orbal-net.ts` + `orbal_net_*` tools + `connector/` and the
bob-l1-spike's proven L1 pieces (seeded into the clone at `docs/reference/`) - productionize
them, do not restart from scratch. Grounded in RFC sections named per item:
- Durable all-day human front-end (RFC S4): a terminal client over ONE durable eve session
  keyed by a stable `bob:<host>` continuation token that RESUMES on relaunch. Productionize
  the spike's proven thin session-stream client into the real rendering layer reusing
  `@ai-sdk/tui`'s render primitives (markdown, tool cards, approval prompts) where reusable;
  if `@ai-sdk/tui` cannot be driven over a durable session (spike's flagged finding), fall
  back to the render-primitives-as-thin-client approach the spike proved. Carry the spike's
  `fetchWithRehydrateRetry` (bounded retry across the post-restart rehydrate window).
- notify_human tool, hardened (RFC S5): relays a mission-room turn into the concurrently-
  live human session (POST to bob's own agent on the human continuation token). Carry the
  rehydrate-retry AND add the park-gate durability belt the spike flagged (deliver ->
  wait-for-park -> release) so a crash between the human turn and the relay cannot silently
  lose it.
- Multi-room native channel + connector attach/detach (RFC S5 + S8, open question #3 - the
  genuinely NEW capability): bob joins ONE `mission-<feature>` room per active mission and
  never a `squad-<lead>` room, N concurrent mission-room sessions under the single
  `orchestrator` identity (NOT `bob` - the seat handle stays `orchestrator`, S8). The
  connector must support INCREMENTAL attach/detach on an already-running process: attach a
  new `(orchestrator, mission-<feature>)` subscription without dropping any other mission's
  frames; detach one without touching the rest. Additive to the proven per-`(room,agent)`
  cursor/`--since` mechanics, not a redesign. Message direction inverts (bob originates
  tasks via `orbal_net_send`, receives reports) - an instructions/skills change, not a
  wire-contract change.
- Orchestration tools (RFC S6): `spawn_up`/`spawn_down`/`spawn_status`/`spawn_poke`/
  `spawn_bridge_pr` as `agent/tools/*.ts`, each a thin typed wrapper shelling out to the
  EXACT `spawn.py` subcommand (argv byte-for-byte identical), plus a minimal `herdr_*` set
  scoped to only the calls `spawn-team.md` actually issues (e.g. read a stalled pane), plus
  a `plan_pane_open`/`plan_pane_selection`/`plan_pane_close` trio wrapping the existing
  `orchestration/plan_pane.py` unchanged. `spawn_bridge_pr` and `spawn_down` (hard to
  reverse) are configured APPROVAL-REQUIRED in bob's agent/tool config; every tool call
  streams to the human TUI. Verify the exact eve tool-approval mechanism from current docs
  (RFC open question #5) and demonstrate the approval prompt fires.
- Eve-skills port (RFC S7): `/scope-mission` -> `agent/skills/scope-mission/SKILL.md` and
  `/spawn-team` -> `agent/skills/spawn-team/SKILL.md`, near-verbatim (frontmatter
  `description` as routing hint; `$ARGUMENTS` -> inline extraction in the body; every
  orbal-net/spawn.py/herdr/plan-pane action becomes the typed tool from S6; file writes via
  the sandbox `write_file`). The interactive interview falls out of the ordinary turn loop
  (S7 verdict: LOW-stretch); the two known stretch points (`AskUserQuestion`'s structured
  widget degrades to free-text Q&A; the plan-pane loop is a wrapped tool) are handled, not
  silently dropped.
- Dual-role wiring: one bob project that runs as the leaf worker (existing behavior, via
  spawn.py's `eve` harness in a squad room) OR as the L1 orchestrator (new: human session +
  N mission rooms). State the switch (env/config/instructions) cleanly; do not regress the
  proven leaf role.
- In-VM coexistence proof harness + VERDICT (the mission's acceptance gate, RFC S9 step-4
  claim proven at the simulated-lead level): launch bob-as-L1 against SIMULATED leads
  (scripted posts/reads on a throwaway `mission-<test>` room on the mission's own orbal-net
  server); assert (1) indistinguishability - `orbal-net peek`/`events` show the
  `orchestrator` identity originating tasks and behaving exactly like a claude L1 (à la
  bob-demo.evidence.md); (2) notify_human relays a simulated lead report up into the live
  human session exactly-once/in-order; (3) multi-room - attach a 2nd `mission-<test2>` room
  and confirm no cross-talk, no dropped frames on either, then detach one cleanly; (4) the
  approval-gated tools prompt before acting. A `VERDICT.md` (GO/NO-GO per claim, commands +
  observed output) in the repo.

## Non-goals
- The REAL host-level launch is OUT of scope for this mission: bob actually spawning a LIVE
  claude/codex/pi fleet via host herdr + `spawn.py up` (RFC S9 step 4 in the real), and
  exercising `spawn_bridge_pr`/`spawn_down` against a real remote under approval (step 5),
  and the full scope-to-teardown live cycle (step 6), and cutover (step 7). These need host
  herdr/orbal-net/spawn.py and human-in-the-loop approval; the ORCHESTRATOR runs them on the
  host AFTER this code lands. In-VM, the `spawn_*` tools are verified by argv-correctness /
  dry behavior and the coexistence claim by SIMULATED leads at the orbal-net level - do NOT
  attempt to nest a real spawn.py/herdr fleet inside the mission VM.
- No remote/Vercel-DEPLOYED orchestrator. Local-first `eve start`, sharing the LAN with
  orbal-net, exactly as the leaf and the spike.
- Do NOT modify `spawn.py`, `AGENTS.md`, or the orbal-net wire contract - bob wraps the
  existing `spawn.py` subcommands as-is (RFC S6 non-goal). One narrow exception is allowed
  only if strictly required and flagged for orchestrator review; default is zero edits.
- Do not regress or redesign the proven leaf role, the native-channel wire contract, the
  connector's exactly-once/cursor/resume, or indistinguishability - all GIVENS (bob-demo,
  eve-harness-v0, bob-l1-spike). Reuse; extend additively.
- No entity or memory-fact writing.

## Constraints
- Ground on and reuse the proven stack (seeded into the clone `docs/reference/`): the
  bob-orchestrator RFC (S4/S5/S6/S7/S8/S9/S10 - authoritative), the bob-l1-spike proven
  sources (the human channel, notify_human, the session client with `fetchWithRehydrateRetry`,
  the two proof runners) + its VERDICT, and the leaf harness already in the repo. The spike
  proved BET 1 (durable rehydrate) and BET 2 (notify_human multiplex incl. the mid-turn
  race) GO - consume those as proven, do not re-litigate; this mission productionizes and
  adds the multi-room + tools + skills + dual-role surface the spike deliberately skipped.
- eve environment (from eve-harness-v0.handoff.md secs 4-5, authoritative): pin `eve@0.22.1`
  + Node >=24 (baked in the VM). `eve start` (production, port 3000) RESUMES durable
  sessions; `eve dev` does NOT. Wipe `.workflow-data` per local run. eve model calls need
  Vercel AI Gateway: `vercel link --yes --project bob --scope zico-ios-projects` writes
  `.env.local` with a fresh `VERCEL_OIDC_TOKEN`; `npx eve link` needs a TTY and will not
  work non-interactively. Do not rediscover this - it is documented.
- eve does NOT durably queue concurrent deliveries to one continuation token - which is why
  the human session and each mission-room session use DIFFERENT tokens; preserve that, and
  keep the connector's strict per-`(room,agent)` serialization (park-gated cursor commit).
- No em dashes anywhere; use "-". Consistent vocabulary (herdr, orbal-net recv/peek/send/
  event, continuation token, session/turn, mission-<feature>/squad-<lead>, orchestrator seat).
- Ships to a GitHub repo (`zico-io/bob`): the orchestrator bridges every live GitHub step
  (push + PR via `spawn.py bridge-pr bob-l1-build`); agents have no `gh`/network and their
  clone origin is a local mirror - prepare the branch/commits + any PR text as files, the
  orchestrator executes the push/PR. Deliverable is the built harness + `VERDICT.md`
  committed to the mission branch; remove the seeded `docs/reference/` throwaway before final
  (or the lead moves proven code into place and drops the reference dir).

## Acceptance criteria
- `/Users/percules/dev/bob` builds and runs on `eve start` (`eve@0.22.1`, Node >=24) in BOTH
  roles: the proven leaf worker (unregressed) AND the new L1 orchestrator.
- Launching bob as L1 opens/attaches a durable `bob:<host>` human session that resumes the
  same conversation across an `eve start` kill+restart (the spike's Proof A property, now in
  production code).
- The in-VM coexistence harness runs and shows PASS on all four claims: (1) indistinguishable
  `orchestrator` identity originating tasks + behaving like a claude L1 in `peek`/`events`;
  (2) notify_human relays a simulated lead report up exactly-once/in-order; (3) multi-room
  attach of a 2nd mission room with no cross-talk / no dropped frames, then clean detach;
  (4) `spawn_bridge_pr`/`spawn_down` prompt for approval before acting.
- The orchestration tools exist as typed `agent/tools/*.ts`, each shelling out to the exact
  `spawn.py`/`herdr`/`plan_pane.py` command (argv verified identical); approval-gating on the
  two hard-to-reverse tools is demonstrated.
- `/scope-mission` + `/spawn-team` exist as `agent/skills/*/SKILL.md`, loadable by name, with
  the tool-call substitutions applied and the two stretch points handled.
- `VERDICT.md` states GO/NO-GO with commands + observed output. No factual conflict with the
  RFC, the spike, the leaf v0 contract, or the post-push orbal-net model. No em dashes.
- A short PR body prepared for the orchestrator to bridge to `zico-io/bob`, and a crisp
  host-run playbook (the exact commands the orchestrator runs on the host to do the real
  step-4/5 launch + bridge/teardown validation).

## Affected areas
- `/Users/percules/dev/bob` (mission clone at `/work`): new `agent/channels/bob.ts` (human
  front-end) + the TUI client, new `agent/tools/{spawn_*,herdr_*,plan_pane_*,notify_human}.ts`,
  new `agent/skills/{scope-mission,spawn-team}/SKILL.md`, connector attach/detach additions,
  dual-role instructions/config, a coexistence harness (e.g. `proofs/coexistence.ts`),
  `VERDICT.md`. Reuses existing `agent/channels/orbal-net.ts`, `agent/tools/orbal_net_*.ts`,
  `connector/` unchanged where possible.
- Seeded reference (orchestrator adds to the clone, agents remove before final):
  `docs/reference/` = the RFC + the bob-l1-spike proven sources + spike VERDICT.
- New PR to `zico-io/bob` (orchestrator-bridged). No `.botfiles` changes.

## Risks and unknowns
- Multi-room connector attach/detach (RFC open Q#3) is the genuinely NEW, un-prototyped
  capability - the spike used ONE room. Cross-talk (a frame for mission A minting a turn on
  mission B's token) and dropped frames on attach/detach of a live process are the real
  hazards; the coexistence harness must exercise 2 rooms + a detach explicitly, not assume.
- eve tool-approval mechanism (RFC open Q#5): the exact `agent.ts`/tool-config surface for
  approval-required vs auto-run is unverified in the fetched docs. Confirm from current docs
  first; if eve has no first-class approval gate, flag it and fall back to a human-typed-only
  path for the hard-to-reverse tools (do not ship an autonomous irreversible GitHub write).
- `@ai-sdk/tui` over a durable session: the spike deliberately used a thin raw client and
  flagged that `@ai-sdk/tui`'s render primitives may not be reusable outside `runAgentTUI`.
  Do NOT let TUI-rendering polish block the durable-session behavior; ship the proven thin-
  client path if the fancy rendering does not cleanly attach, and flag it.
- Dual-role regression: the leaf role is proven and in production use - the L1 additions must
  not break it. Keep a quick leaf-role sanity check green.
- Cross-squad dependency: the coexistence harness (runtime-lead) needs the tools + skills
  (tooling-lead) to be indistinguishable-driving-complete. Sequence: tooling-lead delivers
  the tools first; runtime-lead integrates them into the proof. The orchestrator coordinates
  the handoff in the mission room.
- Two workers on one eve project can collide: each lead scaffolds/fixes its squad's shared
  shape before its workers diverge; workers own isolated files (channels/bob.ts vs connector
  additions; tools/*.ts vs skills/*), not shared source.

## Team plan
- repo: `/Users/percules/dev/bob`
- **runtime-lead** (claude/opus): owns bob's agent runtime and the acceptance gate - the
  dual-role wiring, integrating the durable human session + the multi-room native channel,
  AND the in-VM coexistence harness + `VERDICT.md` + the host-run playbook + the PR-body text.
  Scaffolds the shared project shape first; integrates the tooling squad's tools/skills into
  the proof; relays bridge asks. Coordinates the tooling handoff with the orchestrator.
  - **worker-session** (claude/sonnet): the durable all-day human front-end (RFC S4) - the
    `bob:<host>` durable session + the terminal/TUI client (productionize the spike's proven
    session-stream client, reuse `@ai-sdk/tui` primitives where they attach) with
    `fetchWithRehydrateRetry`, and the hardened `notify_human` tool (rehydrate-retry +
    park-gate belt, RFC S5).
  - **worker-connector** (claude/sonnet): the multi-room native channel + connector
    attach/detach (RFC S5 + S8, open Q#3) - N `mission-<feature>` sessions under the single
    `orchestrator` identity, incremental attach/detach on a live connector with no cross-talk
    / no dropped frames, task-origination direction. Extends the proven connector additively.
- **tooling-lead** (claude/opus): owns the orchestration surface - the eve tools and the
  skills port - and delivers them to runtime-lead for the coexistence proof. Verifies the
  eve tool-approval mechanism (RFC open Q#5) and the argv-identical `spawn.py` wrapping.
  - **worker-tools** (claude/sonnet): `agent/tools/{spawn_up,spawn_down,spawn_status,
    spawn_poke,spawn_bridge_pr}.ts` + minimal `herdr_*` + the `plan_pane_*` trio (RFC S6),
    each argv-identical to today's command; `spawn_bridge_pr` + `spawn_down` approval-gated
    with the approval prompt demonstrated.
  - **worker-skills** (claude/sonnet): port `/scope-mission` + `/spawn-team` to
    `agent/skills/*/SKILL.md` (RFC S7) - near-verbatim body, frontmatter routing hint,
    `$ARGUMENTS` inline extraction, tool-call substitutions, the two stretch points handled.
