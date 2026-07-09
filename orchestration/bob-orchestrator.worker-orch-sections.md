# worker-orch draft: sections 5, 6, 8 (+ raw material for 9, ranked items for 10)

For rfc-lead to fold into `orchestration/bob-orchestrator.rfc.md`. Grounded against
`orchestration/eve-harness.rfc.md` (S3, S5, S6, S7, S8, S10 consumed as proven givens),
`orchestration/eve-harness-v0.handoff.md`, `orchestration/bob-demo.evidence.md`,
`.botfile/memory/tools/orchestration.md`, `orchestration/spawn.py`, and one fresh fetch of
[eve-docs: concepts] (https://vercel.com/docs/eve/concepts, 2026-06-19) to confirm the
sandbox claim used in section 6.

---

## 5. L1-as-native-channel orchestration design

**Position:** bob-at-L1 joins `mission-<feature>` rooms as the exact same native eve
channel mechanic already proven for the leaf role - `agent/channels/orbal-net.ts`, one
external connector holding `recv --follow`, each pushed frame becoming a durable turn via
`send(text, {continuationToken})` - not a new mechanism [eve-harness.rfc.md S5;
eve-harness-v0.handoff.md secs 2-3, proven end to end in the PoC and confirmed
indistinguishable in a live fleet, bob-demo.evidence.md]. Nothing about the wire contract,
the connector's park-gated exactly-once cursor, or the eight event kinds changes for L1;
this RFC consumes all of it as a given.

**What inverts.** A leaf worker joins exactly one `squad-<parent>` room, blocks for tasks,
and reports up. bob-at-L1 joins one `mission-<feature>` room **per mission it is actively
driving** and never a `squad-<lead>` room - the same membership boundary that keeps the
orchestrator from ever messaging a worker directly today (AGENTS.md orchestration
protocol) now holds structurally, because bob's channel simply is not subscribed to any
squad room, rather than holding by prompt discipline. Message *direction* also flips: a
leaf's turns are almost all inbound task descriptions it must act on and answer; bob's
mission-room turns are inbound **reports** from leads, and bob's own tool calls are what
*originate* tasks (`orbal_net_send` posting a task down to `mission-<feature>`, mirroring
what a human orchestrator types today). The turn/tool mechanics are identical in both
directions - a message is a message regardless of who sent it - so this is a change to
bob's instructions and skills (the "brain"), not to the channel or connector contract.

**Session cardinality generalizes, it does not change shape.** The parent RFC already
establishes that one eve agent can hold multiple concurrent sessions keyed by
`<room>:<agent>` continuation tokens - a lead's fixed two rooms need no new primitive
[eve-harness.rfc.md S7]. bob-at-L1 is the same fact at higher multiplicity: N concurrently
driven missions is N `mission-<feature>` sessions on one agent, not a new eve concept. The
3-layer cap is still enforced **per mission** (section 8); running several missions
concurrently is several independent 3-layer trees sharing one L1 identity, not a fourth
layer.

**Bridging the human session and the mission-room sessions - the concrete new piece.** A
lead or worker never had to reach outside its own rooms; bob does, because the point of
being the human's all-day front end (bet 1, worker-eve S4) is to narrate mission progress
*proactively*, not only when the human asks. Position: a lead's report landing in
`mission-<feature>` triggers a turn on that mission's session; that turn's tool code, after
handling the report (logging it, deciding next steps), calls a small `notify_human` tool
that does exactly what the connector already does for an inbound orbal-net frame - a short
`POST /eve/v1/session` **against bob's own agent**, targeting the human-facing session's
continuation token, carrying a short system-authored summary. This is not a new eve
primitive: it is the same session/continuationToken mechanism from [eve-docs: concepts]
(`POST /eve/v1/session`, `x-eve-session-id`, resume via continuation token) invoked by a
tool instead of by the connector's webhook. It works because sessions belong to the agent,
not to a specific channel, and a running turn can make outbound HTTP calls like any other
tool. This keeps the human session and each mission session as genuinely separate
sessions (distinct conversation histories, matching worker-eve S4's single-durable-session
design for the human side without conflating it with N mission-room histories), bridged
only through this one narrow, purpose-built tool. Flagged as an open question (section 10):
whether concurrent turns across two sessions of the same agent (a mission-room turn calling
into the human session while the human session may itself be mid-turn) queue or race is
unspecified in the fetched docs, the same class of gap the parent RFC flagged for
same-session concurrent frames [eve-harness.rfc.md S10 risk 4] - needs the same kind of
spike before this is load-bearing.

**Sequence sketch, both directions** (aligns with worker-eve's S4 framing: one human-TUI
session plus N mission-room sessions is N+1 concurrent sessions under one bob identity).

Direction 1 - human/skill produces a brief, bob relays it down to a lead:

```
human session (bob)                mission-<feature> continuation token       orbal-net server        lead (claude, squad room)
  /scope-mission produces brief -->|
  model calls orbal_net_send tool -->|-- POST /send {room: mission-x, text: brief} -------->| message lands
                                                                                              |-- SSE push, lead's own recv --> lead reads brief, relays to squad-<lead>
```

This is a normal outbound tool call from the human session, not a channel event - identical
in shape to `orbal_net_send`/`orbal_net_event`/`orbal_net_progress` already defined for the
leaf role [eve-harness.rfc.md S5]; the only difference is which session (human vs a mission
room) the model happens to be reasoning in when it calls the tool.

Direction 2 - a lead's report arrives, bob receives it as an inbound frame -> turn, then
relays it up into the human session:

```
lead (claude, squad room)     orbal-net server        connector          bob's mission-<feature> session      bob's human session
  orbal-net send mission-x -------->|-- SSE push ------->|-- POST /orbal-net/message ---->| turn runs
                                     (msg tagged for                                        |-- notify_human tool
                                      mission-x's                                           |     POST /eve/v1/session
                                      continuation token)                                   |     {continuationToken: human}
                                                                                             |------------------------------->| turn appends
                                                                                             |                                 | summary, streams
                                                                                             |                                 | to human's TUI
```

The connector routes each frame to the mission-room session whose continuation token
matches the room it arrived on - exactly the per-`(room, agent)` routing already proven for
a single leaf identity [eve-harness-v0.handoff.md sec 3], just fanned out to N mission rooms
under bob's one `ORBAL_NET_AGENT` identity instead of N separate agent identities.

---

## 6. Orchestration-tools mapping: spawn.py / herdr / GitHub-bridge as eve tools

**Position:** bob wraps today's orchestration shell-outs - `spawn.py`'s subcommands,
the handful of `herdr` calls an orchestrator actually issues, and the GitHub bridge - as
`agent/tools/*.ts`, one typed tool per file, the same primitive already adopted for
`orbal_net_*` [eve-harness.rfc.md S4 tools/*.ts row]. No new capability is invented; each
tool is a thin wrapper that shells out to the exact command a human orchestrator (or a
claude L1) runs today, so this section changes *how* the call is made, not *what* it does.

**Why this is a clean fit for L1 specifically, not a stretch.** A leaf or lead agent's
sandbox is the mission's air-gapped microVM: no `gh`, no network, origin is a local mirror
[AGENTS.md; spawn.py `bridge_pr` comment]. bob-at-L1 is explicitly local-first
(non-goal: no deployed-remote orchestrator), and eve's sandbox model confirms the
consequence: "every eve agent has one sandbox... **on Vercel** it can run on Vercel
Sandbox[,] using ephemeral microVMs for untrusted or model-generated commands" [eve-docs:
concepts, fetched 2026-07-09]. The microVM is a Vercel-deployment detail, not a property of
the sandbox primitive itself - a local `eve dev`/`eve start` process's sandbox is the local
host process and filesystem. bob's one sandbox is therefore the same host shell a human
orchestrator already types into: real `git`, real `gh`, `herdr` on PATH, `spawn.py`
reachable directly. This is the same trust boundary the orchestrator already holds today
(AGENTS.md: "the orchestrator bridges every live GitHub step"), just invoked through a
typed tool call instead of memorized Bash syntax.

**Concrete tool inventory** (mirrors `spawn.py`'s existing subcommands 1:1; no new
subcommands, per the non-goal against modifying `spawn.py`):

- `spawn_up.ts` -> `spawn.py up <roster.json> [teams]`
- `spawn_down.ts` -> `spawn.py down <feature>`
- `spawn_status.ts` -> `spawn.py status <feature>`
- `spawn_poke.ts` -> `spawn.py poke <feature> <role> [msg]` - still needed exactly as today
  for any local-TUI lead/worker (herdr pane-run nudge for an agent idle between `recv`
  calls); unaffected by whether L1 itself is eve or claude [eve-harness.rfc.md S8].
- `spawn_bridge_pr.ts` -> `spawn.py bridge-pr <feature> [title]`
- a small `herdr_*` set, scoped to only the calls `spawn-team.md` actually issues today
  (e.g. reading a stalled pane's recent output) - not the full herdr surface. Keeping the
  tool set to what the orchestrator prompt already exercises matches the tools/*.ts
  minimalism principle (one tool per real need, not a speculative CLI mirror).

**Errors surface as tool failures, not crashes.** `spawn.py validate()`'s three-layer and
room-membership check is untouched and still runs host-side inside `spawn_up`; a rejected
roster becomes a normal typed-tool error the model sees and can react to (re-propose a
roster, ask the human), rather than an opaque process exit the way a raw Bash failure reads
today.

**The GitHub bridge: where it lives now, and whether it collapses.** `bridge_pr()` exists
*because* spawned leads/workers are air-gapped - no `gh`, no network, their clone's origin
is a local mirror (AGENTS.md; spawn.py comments) - so someone with real GitHub access has to
ship their work. But the function has never run *inside* that air gap: it is a plain
`subprocess` call in `spawn.py`, invoked by whatever process is playing L1, and today's
claude L1 already runs bare on the host (spawn.py's own docstring: the orchestrator is "the
pane you are already in ... NOT spawned here", never wrapped by `sandbox_wrap`). bob-at-L1
is local-first for the identical reason (non-goal: no deployed-remote orchestrator) and so
sits in exactly the same position: **`bridge_pr()` does not collapse into a new direct-push
mechanism, because it was never relocated away from L1 in the first place.** The two-step
harvest-then-push ceremony exists for the leads'/workers' benefit (their commits live in an
isolated clone with no route to `origin`), not because L1 lacked access - so nothing about
bob having `gh`/network changes what the function needs to do. `spawn_bridge_pr.ts` therefore
wraps the identical unmodified function the identical way; the only thing that changes is
*how the decision to call it gets made*.

That decision-making change is the actual safety question worth flagging. Today a human
types the command, or a claude L1 chooses to run it as one Bash call among many, visible in
the same transcript the human is reading. With bob, the call becomes a tool the model can
invoke autonomously mid-turn - a live, irreversible, externally-visible GitHub write (a
real push plus a real PR) triggered by model judgment rather than a keystroke. The
human-in-the-loop property is preserved only if it is deliberately re-added at the tool
layer: `spawn_bridge_pr` and `spawn_down` (mission teardown, also hard to reverse) are
configured as approval-required in bob's agent/tool config, mirroring AGENTS.md's "always
confirm first" norm for hard-to-reverse actions, and every tool call streams to the human's
live TUI regardless [eve-harness.rfc.md S3.3, S6.4] so nothing happens off-screen even
between an approval prompt and the human's response.

---

## 8. Three-layer and room-membership mapping with bob at L1

**Position:** `mission-<feature>` maps to one of bob's per-mission continuation-token
sessions (section 5); `squad-<lead>` rooms are completely untouched, still owned and
created by leads exactly as today (`spawn.py bootstrap()`), and bob's channel is simply
never subscribed to one. This is the parent RFC's room-membership rule
[eve-harness.rfc.md S7: "the orchestrator never shares a room with a worker"] enforced one
layer up, by which rooms bob's eve channel joins, not by a new policy.

**Where membership enforcement lives:** unchanged - the orbal-net server, not the harness
[eve-harness.rfc.md S7]. bob is just another orbal-net client subscribing to the rooms its
identity belongs to; nothing about `validate()` or the server's room model needs to know or
care that L1 is now an eve agent instead of a claude pane.

**Join/leave lifecycle: the connector gains an incremental subscription surface.** The v0
leaf connector is symmetric and all-or-nothing: `orbal_net_connector_up` starts it bound to
one `(agent, room)` pair when its eve pane comes up, `orbal_net_connector_down` kills the
whole process at mission teardown [spawn.py `orbal_net_connector_up`/`_down`]. bob's
connector cannot be all-or-nothing the same way, because bob itself is already running when
a new mission starts or an old one tears down (section 5's N+1-sessions point) - killing the
connector to add or drop one mission would drop every other active mission's frames too.
Position: bob's connector supports an incremental **attach/detach** operation on an
already-running process - `spawn_up` (section 6) attaches a new `(bob, mission-<feature>)`
subscription (and, for a fresh mission, first `create-room`/`join`s it, same as today's
`orbal_net_post(..., "create-room", ...)` in `up()`) after the roster is spawned; `spawn_down`
detaches that one subscription and lets `orbal-net serve` for that mission die as it does
today, without touching bob's connector process or any other mission's subscription. This is
a genuinely new connector capability beyond what the leaf v0 needed (flagged for section 10),
though it is additive to, not a redesign of, the proven per-`(room, agent)` cursor/`--since`
mechanics [eve-harness-v0.handoff.md sec 3]. Structurally this is also what keeps bob from
ever leaking into a `squad-<lead>` room: the connector only ever attaches subscriptions for
rooms `spawn_up`/`spawn_down` explicitly name, and those are always `mission-<feature>`,
never a squad room a lead creates on its own.

**bob driving existing claude/codex/pi leads, unchanged - the load-bearing simplicity
point.** This RFC converts only L1. Leads and workers are not touched: a lead is still a
claude/codex/pi terminal agent following its unmodified `spawn.py bootstrap()` prompt,
joining `mission-<feature>`, and blocking on `orbal-net recv` [spawn.py `bootstrap()`].
That bootstrap prompt already treats "the orchestrator" as an opaque identity that posts to
`mission-<feature>` and reads room messages - it has no way to tell, and no reason to care,
whether the process on the other end is a herdr pane running claude or a bob eve session.
This is the exact coexistence property the parent RFC leans on for lead/worker conversion
[eve-harness.rfc.md S9: "a single eve agent in a room is indistinguishable... from a legacy
agent"], applied one layer up: converting L1 requires **zero** changes to L2/L3 bootstrap,
`launch()`, or the `HARNESSES` entries for claude/codex/pi.

**Multiplicity is per-mission, not a new layer.** bob can be mid-flight on several missions
at once (section 5's N mission sessions); the 3-layer cap still applies **per mission** -
any one mission is still orchestrator-leads-workers, <=3 layers, `validate()` unchanged.
Running N missions concurrently is N independent 3-layer trees sharing one L1 identity and
one eve deployment, not a fourth layer or a new hierarchy concept.

**What does NOT change in `spawn.py`'s model of the fleet.** `spawn.py` today explicitly
treats the orchestrator as out of scope for spawning - "the pane you are already in ...
NOT spawned here" (spawn.py module docstring) - and that stays true. Converting L1 to bob
changes **who calls** `spawn.py` (bob's own tools, section 6) and **how** a human starts
that process (`eve start` plus the AI SDK 7 terminal UI, worker-eve S4, instead of opening
a raw claude pane and having AGENTS.md loaded by convention), but it does not add an "eve"
entry to `HARNESSES` for L1 the way the leaf v0 added one for a worker role - `HARNESSES`
describes what `spawn.py up` launches *beneath* L1, and L1 itself was never in that map.

---

## Raw material for section 9 (migration/replacement path) - worker-orch's angle

Ordered list of what changes, tools/spawn.py-facing, once L1 conversion is attempted (for
rfc-lead to weave into the coexist -> cutover sequence; this RFC does not implement any of
it, non-goal):

1. Build the `agent/tools/*.ts` set in section 6 against a throwaway bob project first,
   exercised by hand (not via a mission), confirming each tool's shell-out matches its
   `spawn.py` subcommand's current behavior byte-for-byte (same argv, same exit-code
   handling) before any real mission depends on it.
2. Convert one **already-running** mission's orchestrator seat from a claude pane to bob
   mid-flight is explicitly out of scope for v1 - the first real test is starting a
   **new** mission with bob as L1 from the beginning, against an otherwise-unmodified
   roster/leads, so day one is a clean coexistence test, not a hot-swap.
3. Only after that mission completes with parity (leads/workers cannot tell, section 8) does
   `spawn_bridge_pr`/`spawn_down` get exercised for a real GitHub-visible action, gated by
   the approval-required config from section 6.
4. `AGENTS.md`'s orchestration protocol section does not need rewriting for this step - it
   already describes the room/event contract at the level leads and workers see it; only
   bob's own `instructions.md`/skills need the L1-specific framing, and those are bob's,
   not the shared `AGENTS.md`.

## Ranked items for section 10 (open questions) - worker-orch's angle

1. **Cross-session notify concurrency (section 5).** Whether eve serializes or races two
   sessions of the same agent when one session's tool call creates a turn on another
   (`notify_human` while the human session may itself be mid-turn) is unverified in the
   fetched docs. Same risk class as the parent RFC's same-session ordering question
   [eve-harness.rfc.md S10 risk 4]; needs a spike before `notify_human` is load-bearing.
2. **Tool-approval config for hard-to-reverse tools (section 6).** The fetched docs
   describe AI SDK 7 TUI's "tool-approval prompts" [eve-harness.rfc.md S3.3] but this RFC
   has not verified the exact `agent.ts`/tool-level mechanism for marking a specific tool
   approval-required versus auto-run; needs a doc check before `spawn_bridge_pr`/
   `spawn_down` ship as tools.
3. **Session-count ceiling.** No fetched doc gives a concrete limit on how many concurrent
   sessions one eve agent can hold; bob's per-mission multiplicity (section 5, section 8)
   assumes this scales to "however many missions a human plausibly runs at once," which is
   probably fine but is an assumption, not a verified ceiling.
4. **`herdr_*` tool minimalism.** Section 6 recommends wrapping only the herdr calls
   `spawn-team.md` already issues; the exact list needs a pass against the live skill (once
   ported per section 7) rather than being guessed here.
5. **Incremental connector attach/detach (section 8).** The v0 connector's lifecycle is
   all-or-nothing (one process per mission, started and killed with it); bob's connector
   needs a live attach/detach of individual `(bob, mission-<feature>)` subscriptions on an
   already-running process so one mission's `spawn_down` cannot drop another mission's
   frames. This is new relative to the proven leaf mechanic and has not been prototyped;
   flagged as a build-before-cutover item, same tier as the parent RFC's connector-liveness
   risk [eve-harness.rfc.md S10 risk 2].
