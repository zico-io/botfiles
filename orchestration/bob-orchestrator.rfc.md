# RFC: bob-orchestrator - promoting the eve leaf worker to the L1 orchestration harness

- Status: Draft (north-star architecture RFC; no shipped code)
- Owner: rfc-lead (mission bob-orchestrator)
- Date: 2026-07-09
- Scope: design and prose only. This RFC does not modify spawn.py, AGENTS.md, the bob repo, or orbal-net. It consumes three things as proven givens - the eve-harness RFC (the design of record), the leaf-worker v0 wire contract, and the post-push orbal-net model - and takes a concrete position on each in-scope question rather than surveying options. It is local-first: a remote/Vercel-deployed orchestrator is named as a future increment, not designed here.

---

## 1. Summary and thesis

We run a 24/7 multi-agent product operation as a three-layer fleet - an L1 orchestrator, L2 leads, L3 workers - coordinated over a per-mission orbal-net server and placed by herdr. Today the L1 orchestrator is a claude terminal agent in a herdr pane: the human sits in that pane, scopes missions with it, and it drives leads by typing `orbal-net` CLI commands. It works, but the orchestrator is a generic chat app disciplined by a prompt into calling the CLI at the right moments; nothing in its runtime knows what a room, a turn, or a mission is.

A parallel line of work has already proven a better substrate for the *other* end of the fleet. The eve-harness RFC (orchestration/eve-harness.rfc.md, the design of record) proposed rebuilding fleet agents on Vercel's eve framework, with one defining bet: orbal-net becomes a native eve channel, so a message pushed into a room mints an agent turn automatically, and the eight progress-event kinds become first-class runtime tool calls instead of memorized CLI syntax. That RFC's step 3 was executed in mission eve-harness-v0: exactly one LEAF worker - `bob` - was converted to a local eve agent and run in a live mixed fleet. The bob-demo evidence is unambiguous: orbal-net peek/events/tui cannot tell the eve worker apart from a claude worker - same message shape, same task-start/step/task-done schema, first-class orbal-net identity, connector UP (orchestration/bob-demo.evidence.md). The core mechanic (SSE-frame -> durable eve turn), durability (survived a hard restart AND a real Vercel redeploy), and connector-restart resume were all proven end to end (orchestration/eve-harness-v0.handoff.md S2). spawn.py already carries a first-class local `eve` harness and its connector lifecycle (commit 0d30979).

This RFC proposes the inversion. bob is proven at the BOTTOM of the three-layer model - a leaf that receives tasks. This RFC promotes it to the TOP: the L1 ORCHESTRATION harness, the persistent agent a human launches from the CLI and interacts with throughout the day, that scopes missions and drives leads over orbal-net. It takes two defining bets:

> **Bet 1 - the all-day interactive front-end is eve's AI SDK 7 terminal-UI package over one durable eve session.** The human launches bob from the CLI and talks to it all day in a terminal; the conversation is backed by a single durable eve session (Vercel Workflows, the same durability the leaf PoC proved survives restarts and redeploys), so closing the laptop, a crash, or a redeploy does not lose the thread. bob is a persistent daily companion, not a per-mission process.
>
> **Bet 2 - bob drives leads as a NATIVE eve channel, not CLI shell-outs.** As the orchestrator, bob joins each active `mission-<feature>` room as a native eve channel - the exact same proven leaf mechanic (connector holds the orbal-net SSE stream, each pushed frame becomes a turn keyed by the `orbal-net:<room>:<agent>` continuation token, replies and the eight event kinds are first-class `orbal_net_*` tool calls). The one structural difference from the leaf: an L1 bob is a member of MANY `mission-<feature>` rooms at once (one per live mission), joining and leaving as missions come and go, and it never shares a room with an L3 worker.

Two consequences shape the whole design. First, bob-at-L1 has TWO inbound sources into one agent - the human's TUI turns and the leads' room turns - so section 4 and section 5 must agree on how bob multiplexes a human turn and an orbal-net room turn without breaking the durable-session/cursor contract. Second, bob-at-L1 runs LOCAL on the mission host (it is the pane the human sits in), so unlike the deliberately air-gapped leaf agents it HAS `gh` and network; the GitHub-bridge step the human-facing orchestrator performs today becomes a tool bob calls directly (section 6 takes the precise position - the bridge ceremony itself is unchanged, since it never ran inside the air gap; only the call surface and who decides to invoke it change).

bob is the intended eventual REPLACEMENT for today's claude L1 orchestrator. The migration is incremental and coexistence-first (section 9): because room membership and the wire protocol are unchanged, a bob L1 driving a fleet of existing claude/codex/pi leads is indistinguishable to those leads from today's claude L1 - the same property bob-demo proved at the leaf, now applied at the top. bob can be launched alongside the claude L1 first, then cut over.

This document is a north-star: an RFC a lead could turn straight into a build mission. eve is a Vercel beta; every claim about it is grounded in a current doc (cited inline, consolidated in the appendix) and every beta-churn risk is called out. It consumes the eve-harness RFC's native-channel design (S5), remote/durability analysis (S6), and connector as given, and does not re-open them.

---

## 2. Background: today's L1 orchestrator, and the leaf we are inverting

A reader who knows neither eve nor our stack needs this section; the rest of the RFC builds on it. The three-layer fleet, the herdr/orbal-net split, the post-push coordination model (recv/SSE, consuming vs non-consuming reads, the eight event kinds), and eve's primitives are all established in the eve-harness RFC sections 2 and 3; this section adds only what is specific to the ORCHESTRATOR seat and to the leaf we are promoting.

The four eve terms this RFC leans on, in one breath (fuller treatment in the eve-harness RFC S3): a **channel** is a small adapter that turns an inbound event - a webhook, a chat message, an orbal-net room frame - into a request against the agent; a **session** is one durable, resumable conversation or task, persisted in Vercel Workflows so it survives process restarts and long pauses; a **turn** is one unit of work inside a session (an inbound message, the model's streamed response, and any tool calls it makes along the way); and a **continuation token** is the stable string that names a session, so a later call carrying the same token reattaches to that same durable conversation instead of opening a new one. bob's whole design is an exercise in which token addresses which session (sections 4 and 5).

### 2.1 What the L1 orchestrator does today

The L1 orchestrator is layer 1 of the mission hierarchy: the human-adjacent pane (AGENTS.md orchestration protocol). It is NOT spawned by spawn.py - it is "the pane you are already in" (orchestration.md; spawn-team.md). Its job splits cleanly into two kinds of work:

- **Coordination (messages).** It sets the mission brief, relays tasks to leads in each `mission-<feature>` room, monitors progress, and collects results - all as orbal-net messages and reads. It is a member of every active `mission-<feature>` room and, by the membership rule, never shares a room with an L3 worker, so it structurally cannot message a worker directly (orchestration.md). It blocks on `orbal-net recv` for the next inbound message; shell poll loops are forbidden (orchestration.md).
- **Placement / process / lifecycle (not messages).** It stands fleets up and down with spawn.py (`up`/`down`/`poke`/`status`), and it is the sole holder of the live GitHub bridge: because spawned agents have no `gh`, no network, and a local-mirror clone origin, the orchestrator harvests each mission branch and opens the PR via `spawn.py bridge-pr` (spawn.py; AGENTS.md). It also runs the two interactive orchestration skills, today claude-code slash commands: `/scope-mission` (interview the human, write the brief + roster, driven through a live plan pane) and `/spawn-team` (pick the minimum teams, call `spawn.py up`, drive the fleet).

Everything in the first bullet is coordination this RFC re-homes onto the native channel (section 5); everything in the second is placement/lifecycle this RFC re-homes onto eve tools and skills (sections 6 and 7).

### 2.2 The leaf we are inverting: bob at L3

Mission eve-harness-v0 converted one L3 leaf worker to a local eve agent, `bob`. The proven shape (eve-harness-v0.handoff.md; spawn.py commit 0d30979):

- bob runs `eve start` - the eve production server (port 3000) that RESUMES durable sessions - in a herdr pane inside the mission VM, LOCAL, sharing the LAN with orbal-net (so its outbound tools reach orbal-net directly; a deployed agent could not, which is why v0 was local-first).
- A small always-on **connector** runs alongside it: it holds one `orbal-net recv <room> --follow` subscription, and on each pushed frame POSTs `{room, agent, text, msgSeq}` to bob's eve channel, which mints a turn keyed by the `orbal-net:<room>:<agent>` continuation token. The connector is the sole owner of the read cursor and serializes strictly per (room, agent) - deliver one frame, wait for the session to park, commit the fsync'd cursor, read the next - which is what makes exactly-once (zero lost, zero dup) hold.
- bob's replies and its eight progress-event kinds are first-class `orbal_net_send`/`orbal_net_event`/`orbal_net_progress` tool calls, not CLI shell-outs.
- spawn.py's `eve` harness injects `ORBAL_NET_ROOM=squad-<parent>` (the leaf is in exactly one squad room) and runs the connector lifecycle (`orbal_net_connector_up`/`down`/`status`, symmetric to the server), so a dead connector is surfaced by `status`.

This RFC inverts that leaf into an orchestrator by changing three things and keeping the mechanic: (1) the front-end becomes an all-day human-interactive TUI over a durable session rather than a headless `eve start` pane (section 4); (2) the injected room set becomes the N live `mission-<feature>` rooms rather than one `squad-<parent>` (section 5); (3) bob gains placement/lifecycle eve tools and the orchestration skills, and - being LOCAL - absorbs the GitHub bridge (sections 6, 7). The room-membership rules, consuming/non-consuming semantics, the eight event kinds, and the wire contract are all unchanged - they are inherited from the proven leaf, and this RFC does not touch them.

---

## 3. eve primitives delta for an orchestrator

`orchestration/eve-harness.rfc.md` S3 already covers eve's primitives for a leaf worker: instructions.md, agent.ts, tools/*.ts, subagents/*, channels/*, connections/*, sandbox/*, and names skills/* and schedules/* in passing without detail (S3.1), and covers the AI SDK 7 terminal-UI package briefly as a scope-limited primitive no leaf worker needs (S3.3). bob-at-L1 is the first role in this fleet that needs three of those previously-skimmed primitives load-bearingly: the terminal-UI package (bob's human-facing front end, section 4), skills (the two ported commands, section 7), and schedules (a new capability bob gains that no leaf worker needs). This section covers only that delta - what a leaf worker's RFC did not need to say.

### 3.1 AI SDK 7 terminal-UI package, precisely

`@ai-sdk/tui` ships `runAgentTUI({ agent })`, which "enables running a ToolLoopAgent in an interactive terminal" for "local development, demos, and internal tools where a terminal experience is enough and you do not want to build a custom UI" [ai-sdk-docs: terminal-ui]. It renders "prompt input, streamed assistant responses, markdown rendering, tool cards, reasoning sections, scrolling, and tool approval prompts" [ai-sdk-docs: terminal-ui], and "runs until the user exits with Esc or Ctrl+C" [ai-sdk-docs: terminal-ui] - the docs make no claim of session persistence, resumption, or conversation storage across restarts, and the call signature (`runAgentTUI({ agent })` against an in-process `ToolLoopAgent`) explains why: the TUI drives a live agent object in the calling process's own memory, not a remote durable session reached over HTTP.

This is the exact tension section 4 exists to resolve. `runAgentTUI` alone is a rendering surface bolted directly onto a volatile in-process agent - the opposite of "one durable eve session so the conversation survives restarts." Section 4 states the position: bob does not call `runAgentTUI({ agent })` against a bare in-memory agent. It reuses the TUI's rendering primitives (markdown, tool cards, reasoning, approval prompts) as a client attached to bob's own durable eve session/turn stream (`POST /eve/v1/session`, `GET /eve/v1/session/<id>/stream` [eve-docs: concepts]) - the same session API a channel, such as the orbal-net channel from eve-harness.rfc.md S5, calls into. Durability lives in the session, not in the terminal process.

### 3.2 Skills

`agent/skills/*` are markdown playbooks the model loads on demand rather than carrying in the always-on prompt [eve-docs: concepts]. The smallest skill is one file, e.g. `agent/skills/forecast.md`; a packaged skill needing supporting files is a directory with a `SKILL.md` plus siblings (`references/`, `assets/`, `scripts/`) [eve-docs: skills]. `SKILL.md`'s frontmatter carries a `description` written as a routing hint ("Use when the user needs a release checklist or changelog workflow") [eve-docs: skills]; a flat markdown skill without frontmatter has its description auto-extracted from the first non-empty body line [eve-docs: skills]. eve exposes each skill's description to the model plus a framework-owned `load_skill` tool; a request matching a description, or explicitly naming the skill, makes the model call `load_skill`, which appends that skill's markdown into the active turn's context [eve-docs: skills]. This is progressive disclosure: the description is always visible and cheap, the body loads only when relevant - the same shape our own `.claude/commands/*.md` files already follow, loaded by Claude Code's own skill system rather than eve's.

Directly relevant to section 7: "Skills authored against the Agent Skills standard port as-is to eve's framework, enabling reuse across compatible systems" [eve-docs: skills]. Take this portability claim seriously but verify it empirically before relying on it (beta-risk register, section 11) - it is why section 7 treats `/scope-mission` and `/spawn-team` as a near-direct frontmatter-plus-body port rather than a rewrite.

### 3.3 Schedules

`agent/schedules/*` start a turn on a cron clock instead of an inbound message - "for daily digests, data syncs, cleanup sweeps, heartbeats, or anything that should fire on a cadence" [eve-docs: schedules]. `defineSchedule({ cron, markdown })` (a fire-and-forget prompt) or `defineSchedule({ cron, run })` (a handler function), with a standard 5-field cron string evaluated in UTC on Vercel [eve-docs: schedules]. Locally, `eve dev` never fires a schedule on its cadence - it exposes a manual one-shot dispatch route (`POST /eve/v1/dev/schedules/<id>`) for out-of-band testing. `eve start` - the production server bob runs, per S9 step 3's precedent for the leaf-worker role - does fire schedules on their real cadence: on Vercel each becomes a native Cron Job, and self-hosted it runs on Nitro's task runner for as long as that process stays up [eve-docs: schedules]. No leaf worker in this fleet has ever needed a clock-driven turn; bob is the first role for which "check something periodically without a human or a room message triggering it" is in scope (a stale-mission sweep, a scheduled status digest, a heartbeat). This RFC does not design that capability - it is flagged as a candidate in section 10's open questions, out of scope here per the non-goals (no code, no new orchestration behavior beyond what is asked).

---

## 4. Interactive all-day session design

**Position:** bob's all-day human-facing front end is a custom terminal client - built from `@ai-sdk/tui`'s rendering primitives, not a bare `runAgentTUI({ agent })` call against an in-memory agent - that attaches to one durable eve session per human, addressed by a stable continuation token, and reconnects to that same session's stream on every launch. The human never restarts a conversation with bob; they resume one.

### 4.1 Why stock `runAgentTUI` cannot be the front end as-is

Section 3.1 established the gap: `runAgentTUI({ agent })` drives an in-process `ToolLoopAgent` and preserves nothing when the user hits Ctrl+C [ai-sdk-docs: terminal-ui] - the opposite of "one durable eve session so the conversation survives restarts." Two properties are worth keeping from it rather than hand-rolling a terminal UI from zero: the rendering (markdown, tool cards, reasoning display, scrolling) and the approval-prompt flow, both cited as first-class in the package [ai-sdk-docs: terminal-ui]. The position: reuse the TUI's render loop but change its input/output wiring so it is not driven by a local `ToolLoopAgent`'s in-memory event emitter, but by eve's session stream (`GET /eve/v1/session/<id>/stream`, an NDJSON stream of lifecycle events [eve-docs: concepts]) for input, and a `POST` to that same session carrying the durable `continuationToken` for output - exactly the shape the orbal-net channel already uses for a room message (eve-harness.rfc.md S5). This is not a new integration pattern; it is the same "session is durable, front end is a thin resumable client" shape S5 already established for the orbal-net channel, applied to a human instead of a room.

**Flagged verdict, stated plainly (the central unknown this RFC was asked to investigate):** the fetched current docs give no evidence that `runAgentTUI({ agent })`, used as documented, cleanly rides a long-lived durable eve session out of the box - its contract is explicitly local/in-process/until-exit [ai-sdk-docs: terminal-ui], with no mention of `continuationToken`, session reattachment, or Workflow-backed state anywhere in that page. The parent RFC independently flagged the same gap: `@ai-sdk/tui` "connects directly to an agent instance for immediate local development and testing, not designed for remote deployment," and names `@ai-sdk/workflow`'s `WorkflowAgent` - not the TUI package - as the durable, resumable counterpart [eve-harness.rfc.md S3.3, citing ai-sdk-blog: ai-sdk-7]. Do not overclaim a clean out-of-the-box fit that no fetched source documents. The fallback this RFC commits to instead is stated above: the TUI is a thin client against a durable server-held session, not a `runAgentTUI` call holding state in-process - concretely, this likely means driving `@ai-sdk/tui`'s underlying render primitives directly (or fronting a `WorkflowAgent`-backed session with the same rendering layer) rather than calling the documented `runAgentTUI({ agent })` entry point unmodified against a local agent object. Exactly how much of `@ai-sdk/tui`'s internals are reusable outside its own documented entry point is unresolved from the docs fetched for this RFC and is carried into section 10 as the single highest-risk unknown in this design.

### 4.2 "Launches bob via CLI"

Launching bob is starting (or attaching to) the local `eve start` production server for bob's agent project and pointing the terminal client at bob's own fixed continuation token (e.g. `bob:<host-identity>`, a human-scoped analog of the `orbal-net:<room>:<agent>` token S5 defines for room channels). `eve start` resumes durable sessions; `eve dev` does not - the same distinction the eve-harness-v0 mission already established for the leaf-worker role (eve-harness-v0.brief.md Constraints) applies unchanged to bob. On the first-ever launch there is no session yet, so the client's first message opens one; on every subsequent launch (fresh terminal, machine reboot, an `eve start` process restart) the client attaches to the session that already exists for that token, and the human's next message is simply the next turn in the same durable conversation. "Launching bob via CLI" is attach-or-create, not always-create - the human should not be able to tell "I closed my laptop and reopened bob" apart from "eve's session process cold-started and Workflows replayed it" [eve-docs: concepts], because both are the same event from the session's point of view: a turn arriving after a pause.

### 4.2b Concrete walkthrough: launch, talk all day, close the laptop, reopen

This is the scenario the acceptance criteria ask for stated end to end, tying 4.1 and 4.2 together:

1. Human runs the bob launch command in a terminal. This starts (or finds already-running) bob's local `eve start` production server, then starts the custom TUI client from 4.1, which resolves bob's fixed human-facing continuation token and calls `POST /eve/v1/session` (first launch ever: no session exists yet, so this opens one) or attaches to the existing session's stream via `GET /eve/v1/session/<id>/stream` (every later launch).
2. The human converses normally for hours: types a message, the client POSTs it to the session with the continuation token, the TUI renders the streamed turn (markdown, tool cards, reasoning) exactly as `@ai-sdk/tui` already does for a live agent [ai-sdk-docs: terminal-ui], except the state backing it lives in eve's Workflow-backed session rather than the client's own memory. bob relays mission-room activity into this same stream via the `notify_human` tool section 5 defines, so the human sees both their own conversation and proactive updates in one thread.
3. The human closes the laptop. Nothing explicit happens to the session - it is not "ended," only unattended. Any turn already in flight checkpoints and pauses the way any eve turn does between tool calls or while waiting on a room reply [eve-docs: concepts].
4. The human reopens the laptop, possibly hours or days later, and reruns the same launch command. The client resolves the same fixed continuation token and reattaches to `GET /eve/v1/session/<id>/stream`. Because the session is durable Workflow state, not process memory, the full prior conversation is still there - the human can scroll back through it - and if anything happened while they were away (a lead's report bob relayed via `notify_human`), it is already sitting in the session as turns the human simply had not read yet, not lost.
5. The human types their next message. It lands as the next turn on the same session, with full history - the model reasons over the same durable conversation it would have if the laptop had never closed. This is the same rehydrate-on-reattach property eve-harness-v0's PoC already proved for a leaf worker's session (a redeploy and a hard restart both resumed a session with the codeword intact, eve-harness-v0.handoff.md section 2) - bob's human session claims nothing new eve-mechanically, only a new caller (a person's terminal, not a room connector).

### 4.3 What actually needs to be durable, and what does not

Durability is a property of the session/turn substrate (eve-harness.rfc.md S3.2), so this design gets it for free at the layer that matters: the conversation, tool calls, and any state bob's tools write into its sandbox. What is explicitly not durable, and does not need to be: the terminal process itself (closing the terminal is not closing the session, the same way closing a browser tab does not end a server-side web session), and anything rendered purely client-side (scroll position, which panel has focus). The local-TUI-versus-durable-session duality the eve-harness RFC already argues for a deployed channel (S6.4) applies here to bob's own front end: the rendering surface is disposable and local, the state behind it is not.

### 4.4 Concurrency: one durable session is not the same session for everything

bob-at-L1 is, per section 5's position, also a native eve channel subscriber to every `mission-<feature>` room it drives - concurrently with the human typing to it directly. That is two potential turn sources into the same agent: the human's terminal client, and an inbound orbal-net frame from a lead's reply. eve's per-continuation-token turn model does not durably queue concurrent deliveries to one token - the eve-harness-v0 mission proved this the hard way for the leaf-worker connector (eve-harness-v0.brief.md Constraints: "eve does NOT durably queue concurrent deliveries to one continuation token"). The position: the human-facing session (token `bob:<host-identity>`) and each mission-room session (token `orbal-net:<room>:bob`, one per room bob is a member of, per section 5) are different continuation tokens, hence different sessions - not one session serving both the human and every room. This sidesteps the concurrent-delivery hazard entirely rather than requiring bob to build its own serialization layer: a human message and a room frame cannot collide, because they never target the same session. The cost is that bob's "all day interactive" experience is deliberately split into N+1 concurrent durable sessions (one human-facing, one per active mission room) rather than a single unified context; this mirrors the session cardinality the eve-harness RFC already establishes for leads (S7: "a lead runs two concurrent durable sessions... a worker runs one") - bob simply has more rooms. What stitches these N+1 sessions into one coherent experience for the human is answered concretely in 4.5; a shared cross-session memory layer for bob's own tools is an open question, flagged in section 10, not resolved here.

### 4.5 What the human sees

bob attaches once to its own human-facing session and stays attached for the terminal's lifetime. Room activity across every mission bob drives becomes visible to the human only through bob relaying it: bob's own turn on a room-facing session (4.4) processes an inbound frame and, when it judges the human should see it, makes a tool call that posts into the human-facing session - not through the human's terminal directly subscribing to N room streams. This keeps the human-facing session the single pane of glass by construction: everything the human sees arrived as a turn in the one session their terminal is attached to, exactly like today's L1 orchestrator pane, which only ever reads `mission-<feature>` and relays selectively rather than being flooded with every squad room's raw traffic.


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
being the human's all-day front end (bet 1, section 4) is to narrate mission progress
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
sessions (distinct conversation histories, matching section 4's single-durable-session
design for the human side without conflating it with N mission-room histories), bridged
only through this one narrow, purpose-built tool. Flagged as an open question (section 10):
whether concurrent turns across two sessions of the same agent (a mission-room turn calling
into the human session while the human session may itself be mid-turn) queue or race is
unspecified in the fetched docs, the same class of gap the parent RFC flagged for
same-session concurrent frames [eve-harness.rfc.md S10 risk 4] - needs the same kind of
spike before this is load-bearing.

**Sequence sketch, both directions** (aligns with section 4's framing: one human-TUI
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

## 7. Eve-skills port of /scope-mission + /spawn-team

**Position:** `/scope-mission` and `/spawn-team` port to `agent/skills/scope-mission/SKILL.md` and `agent/skills/spawn-team/SKILL.md` almost mechanically - frontmatter `description` in place of the `.claude/commands/*.md` frontmatter's `description`/`argument-hint`, body copied over near-verbatim - because the Agent Skills standard both formats already follow is the same shape eve explicitly ports as-is (section 3.2, [eve-docs: skills]). The slash-command UX the brief asks to keep is preserved by bob's instructions.md or a thin routing skill naming the two skills explicitly, since eve's skill loading triggers on the model matching a description OR the user naming the skill outright [eve-docs: skills] - "the human types `/scope-mission bob-orchestrator`" maps directly onto eve's documented explicit-invocation path, no bespoke slash-command parser needed.

### 7.1 What changes, mechanically

- **Frontmatter.** `.claude/commands/scope-mission.md`'s `description: Interview the human to scope an ambiguous mission...` becomes the `SKILL.md` frontmatter `description`, written as the routing hint eve's docs prescribe ("Use when...") [eve-docs: skills]. `argument-hint: <feature>` has no direct eve frontmatter equivalent; state the argument shape in the body's opening line instead - the body already does this today ("The human has a mission whose feature name is `$ARGUMENTS`").
- **Argument substitution.** `$ARGUMENTS` is a Claude Code convention with no eve equivalent; the ported skill body instructs the model to extract the feature name from the human's message inline. This is a prompt-writing change, not a capability gap - the model already performs exactly this kind of extraction from free text for a Claude Code slash command.
- **Interview prompts.** Every `AskUserQuestion` call in the interview loop maps to the model simply asking its question as the next turn's assistant message and reading the human's next turn as the answer. The `/scope-mission` interview is already conversational, not tool-call-heavy, so this is close to a no-op; the one true capability difference is `AskUserQuestion`'s structured multiple-choice UI, which has no cited eve equivalent - the ported skill degrades to free-text Q&A, worth flagging (section 10) rather than silently losing.

**Feasibility verdict on the interactive multi-step interview, precisely.** The question the brief asks is whether eve's `skills/*` primitive can express an interactive, multi-turn interview at all, or only a linear procedure. The answer, from what the docs describe: this is not actually a question about the skills primitive. A skill is inert content - `load_skill` appends one markdown body to the current turn's context once, on match or explicit naming [eve-docs: skills]; nothing in that mechanism models multi-turn state, branching, or waiting for an answer. What makes `/scope-mission` interactive today is not Claude Code's skill-loading step, it is the ordinary agent turn loop underneath it: the model asks a question in one turn's output, the human's next message is the next turn, and the model (with the skill's procedure still in context, since a loaded skill stays in that session's context for the rest of the conversation, not just the triggering turn) reads the answer and continues. eve's session/turn model has exactly that same shape (section 3.2; a session is many turns, each turn can stream text and wait for the next). So: **the interactive interview is not a skills-primitive stretch - it falls out of eve's ordinary turn loop for free, the same way it falls out of Claude Code's.** The genuine, narrower stretch is the two pieces called out immediately above and below this verdict: `AskUserQuestion`'s structured widget (degrades to free text, no eve equivalent found) and the plan-pane's live shared-editor loop (not a turn-loop concept at all in either system - handled below as a wrapped tool, not a skill capability). Mark the skill port itself LOW-STRETCH; mark those two specific UI affordances as the actual stretch points.
- **File writes.** `orchestration/<feature>.brief.md` and `.roster.json` are written via eve's sandbox tools (`write_file`, targeting the agent's sandbox filesystem [eve-docs: concepts]) instead of Claude Code's `Write`. Section 6 (herdr/spawn.py as eve tools) is where the sandbox-versus-mission-clone question this raises gets resolved; this section only notes the skill body's file-write steps need a tool-name substitution, not a logic change.
- **The plan-pane collaboration loop (`orchestration/plan_pane.py`).** Herdr-specific (a live Helix pane split via a herdr socket), with no eve analog - eve's channels are message-in/message-out, not a shared-editor-pane primitive. Position: keep the plan-pane loop as a tool bob calls (a `plan_pane_open`/`plan_pane_selection`/`plan_pane_close` tool trio wrapping the existing `orchestration/plan_pane.py` CLI, unchanged), since bob runs locally on the same host as herdr (thesis bet 2; this RFC's LOCAL-first, non-goal 6) and so can reach the herdr socket exactly like today's claude L1 does. This is the same "wrap the existing CLI as a typed tool" move eve-harness.rfc.md S4 already prescribes for orbal-net/herdr operations generally - no new mechanism, one more CLI wrapped.
- **`/spawn-team`'s drive loop.** Its "post a task, poke, monitor with `herdr wait agent-status`" procedure (spawn-team.md step 4) stays unchanged as a step-by-step description in the skill's markdown, but every individual action it prescribes (`orbal-net send`, `spawn.py poke`, `herdr wait`) becomes a typed tool call per section 6 (orchestration-tools-as-eve-tools), not a shell-out. The `HERDR_ENV=1` precondition check similarly becomes something the tool layer enforces rather than a shell-checked prompt instruction.

### 7.2 What does not change

The interview dimensions (goal, in scope, non-goals, constraints, acceptance criteria, affected areas, risks, team plan), the brief's markdown template, and the roster JSON schema are pure content - none of it is Claude-Code-specific, so none of it needs to change for the port. `up`'s auto-discovery of `<feature>.brief.md` next to the roster and its auto-post into the mission room (spawn.py `up()`, orchestration.md) is unaffected either way; that is spawn.py behavior, not skill behavior, and this RFC's non-goals already rule out modifying spawn.py's core flow beyond the prepared diff sections 6 and 9 describe.

### 7.3 Why this is one of the easier ports

Section 4 of the eve-harness RFC already scored `skills/*` as "clean concept / stretch mechanics... one of the easiest primitives to migrate," for exactly this reason: `.claude/commands/*.md` and eve's `SKILL.md` are both markdown-with-frontmatter, loaded on demand, describing a procedure in prose. The Agent Skills standard's explicit portability claim [eve-docs: skills] means the frontmatter shape itself is likely close to drop-in; the work this section identifies is almost entirely in the tool-call substitutions (7.1), not the prose.


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

**bob's orbal-net identity at L1 stays the existing `orchestrator` handle, not `bob`.** `bob` names the harness and product; `orchestrator` names the seat - exactly as the leaf v0's orbal-net identity was its role (`worker-eve`) and never `eve`. Keeping the handle means `spawn_up`'s room creation under the hardcoded `orchestrator` string (spawn.py `up()`: `orbal_net_post(feature, "orchestrator", "create-room", ...)`) and every lead bootstrap's `parent orchestrator` reference resolve unchanged, with no edit to `spawn.py` or the lead bootstrap - and the indistinguishability property below depends on exactly this: leads see the same `orchestrator` identity posting to `mission-<feature>` whether the process behind it is a claude pane or a bob eve session.

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
that process (`eve start` plus the AI SDK 7 terminal UI (section 4), instead of opening
a raw claude pane and having AGENTS.md loaded by convention), but it does not add an "eve"
entry to `HARNESSES` for L1 the way the leaf v0 added one for a worker role - `HARNESSES`
describes what `spawn.py up` launches *beneath* L1, and L1 itself was never in that map.


---

## 9. Migration and replacement path

bob is the intended eventual REPLACEMENT for today's claude L1 orchestrator. This section is the ordered path from "claude in a herdr pane, driving the fleet by typing `orbal-net`" to "bob, the durable eve orchestrator." It is designed around one structural fact established in section 8: converting L1 touches ZERO L2/L3 surface. A lead is still a claude/codex/pi agent following its unmodified `spawn.py bootstrap()`, and that bootstrap already treats "the orchestrator" as an opaque identity that posts to `mission-<feature>` and reads room messages. It cannot tell, and has no reason to care, whether the process on the other end is a claude pane or a bob eve session - the exact coexistence property the eve-harness RFC proved at the leaf (S9), now applied one layer up. That makes coexistence the default and cutover a per-mission opt-in, not a flag day.

An ordered sequence, each step a shippable state:

1. **Build bob's L1 agent project against a throwaway target.** `instructions.md` folds in AGENTS.md's orchestration protocol plus the L1-specific framing (drive leads, never message a worker, narrate to the human). Reuse the proven leaf `agent/channels/orbal-net.ts` + `orbal_net_*` tools unchanged (section 5). Add the new pieces: the `spawn_*`/`herdr_*` tools (section 6), the `notify_human` bridge tool (section 5), and the ported `/scope-mission` + `/spawn-team` skills (section 7). Exercise each tool by hand and confirm its shell-out matches the corresponding `spawn.py` subcommand byte-for-byte - same argv, same exit-code handling - before any real mission depends on it.

2. **Prove the interactive-durability fit (the central unknown, open question #1).** Launch bob via CLI, hold an all-day-style conversation, then kill and restart the `eve start` process (and separately simulate a redeploy), and confirm the human-facing session rehydrates - the conversation resumes, not restarts (section 4). This is the cheapest test of bet 1 and the riskiest claim in the RFC; it gates everything human-facing.

3. **Prove the multiplex (open question #2).** Attach bob to one throwaway `mission-<feature>` room via the connector AND to the human session at the same time. A lead-simulated frame produces a room turn that calls `notify_human` into the concurrently-live human session; confirm no lost, duplicated, or raced turn across the two sessions of the one agent (section 5). Steps 2 and 3 together are the recommended first increment (section 10).

4. **First real coexistence mission.** Start a NEW mission with bob as L1 from the beginning, against an otherwise-unmodified roster of claude/codex/pi leads and workers. Because L2/L3 are untouched, this is a clean coexistence test, not a hot-swap of a running orchestrator seat (which is explicitly out of scope for v1). Success = leads and workers cannot tell L1 is bob, and `orbal-net tui`/`peek` shows the "orchestrator" identity behaving identically to a claude L1 in every mission room - bob-demo's indistinguishability result, reproduced one layer up.

5. **Exercise the relocated GitHub bridge and teardown under approval.** Only after step 4 completes with parity, drive that mission's real, GitHub-visible PR through `spawn_bridge_pr`, and its teardown through `spawn_down`, both gated by the approval-required tool config (section 6). This is where the bridge-relocation position (a LOCAL bob pushes/PRs directly) first touches a real remote.

6. **Run a full scope-to-teardown cycle through the ported skills.** Drive `/scope-mission` (interview -> brief -> roster, plan pane included) then `/spawn-team` then the fleet, then teardown via the `spawn_down` tool (section 6), end to end with bob, confirming the slash-command UX and the interview loop survive the port (section 7), with the free-text-interview degradation (open question #4) observed in practice.

7. **Cutover: make bob the default L1 launch path.** What actually changes at cutover is small and human-facing: the launch ritual becomes `eve start` plus the terminal UI instead of opening a raw claude pane with AGENTS.md loaded by convention, and the two orchestration skills live in bob's `agent/skills/` instead of `.claude/commands/`. What does NOT change: `spawn.py`'s `HARNESSES` map (L1 was never in it - it describes what `up` launches BENEATH L1), every L2/L3 `bootstrap()`, `launch()`, and `validate()`. `AGENTS.md`'s orchestration protocol section stays as-is - it describes the room/event contract at the level leads and workers see it, which is unchanged; the only edit worth making is a one-line note that the L1 seat may now be bob or claude. The L1-specific behavior lives in bob's own `instructions.md`/skills, not in the shared `AGENTS.md`.

**Future increment, explicitly out of scope here:** a deployed-remote bob (a Vercel deployment rather than a local `eve start`), which re-opens the public-reachability and Vercel-Sandbox git-write-back gaps the eve-harness RFC already owns as its S10 risks 1 and 5. Local-first is a deliberate choice that moots both for the orchestrator seat (bob is the local pane the human sits in), exactly as it did for the leaf v0.

Because every step 1-6 leaves the fleet in a shippable mixed state (a bob L1 or a claude L1, chosen per mission, driving identical leads), there is no big-bang cutover to schedule - step 7 is just "stop choosing claude," reversible at any point by launching the claude pane instead.

---

## 10. Ranked open questions and the recommended first increment

Ranked highest-risk first. Items 1-2 are the two genuinely-new unknowns this RFC introduces beyond the proven leaf; the rest are bounded design work.

1. **Interactive-durability fit - does the terminal UI cleanly ride a long-lived durable session?** This is the thesis's bet 1 and the single sharpest unknown. `@ai-sdk/tui`'s `runAgentTUI` is documented as local, in-process, and non-durable - it preserves nothing across Ctrl+C (section 3.1, [ai-sdk-docs: terminal-ui]). The position (section 4) is to reuse its rendering primitives as a thin client over eve's durable session stream rather than driving a bare in-memory agent, so durability lives in the session. But that exact wiring - render loop attached to `GET /eve/v1/session/<id>/stream` for a mid-turn, interruptible, all-day human loop that rehydrates on relaunch - is not something the fetched docs demonstrate end to end. It must be proven before anything human-facing is built on it (section 9 step 2).

2. **Cross-session concurrency for `notify_human` (both workers flagged this independently).** bob-at-L1 runs the human-facing session and N mission-room sessions concurrently under one agent identity (sections 4.4, 5). When a mission-room turn calls `notify_human` to post into the human session while that human session may itself be mid-turn, does eve serialize or race the two? The fetched docs do not say; it is the same risk class as the eve-harness RFC's same-session ordering question (S10 risk 4). `notify_human` is load-bearing for "bob narrates mission progress proactively," so this needs a spike (section 9 step 3) before it ships.

3. **Membership and identity across many rooms - the connector needs a new incremental attach/detach surface.** bob must be a first-class orbal-net member of EVERY active `mission-<feature>` room and ONLY those, joining and leaving as missions come and go. This is a genuinely new connector capability beyond the proven leaf v0: that connector's lifecycle is all-or-nothing (one process per mission, started and killed with it - spawn.py `orbal_net_connector_up`/`_down`), but bob stays up ACROSS mission boundaries, so its connector must support live attach/detach of an individual `(bob, mission-<feature>)` subscription on an already-running process - `spawn_up` attaches (and first creates/joins) a subscription, `spawn_down` detaches only that one, without dropping any other active mission's frames (section 8). It is additive to, not a redesign of, the proven per-`(room, agent)` cursor/`--since` mechanics, but it has not been prototyped, and it is build-before-cutover, the same tier as the eve-harness RFC's connector-liveness risk (S10 risk 2). Two further sub-unknowns: the session-count ceiling (no fetched doc gives a concrete limit on concurrent sessions per eve agent; bob's multiplicity assumes it scales to however many missions a human plausibly runs at once), and the operational supervision of a subscription set that changes shape over a long-lived bob process. bob never leaking into a `squad-<lead>` room is NOT a risk - it is structural: the connector only ever attaches the `mission-<feature>` rooms `spawn_up`/`spawn_down` name, never a squad room a lead creates on its own.

4. **Skills-primitive fit for the interactive interview.** `/scope-mission` and `/spawn-team` port near-verbatim as `SKILL.md` (section 7), but two mechanics are a stretch: `AskUserQuestion`'s structured multiple-choice UI has no cited eve equivalent, so the interview degrades to free-text Q&A (section 7.1); and `$ARGUMENTS`/argument-hint have no eve frontmatter analog and move into the skill body. Neither blocks the port - the interview is already conversational - but the degraded structured-prompt UX should be observed in practice (section 9 step 6) rather than assumed away.

5. **GitHub-bridge relocation safety, and the tool-approval mechanism.** A LOCAL bob HAS `gh`/network, so the bridge collapses from "the orchestrator harvests and PRs on the air-gapped agents' behalf" into a direct `spawn_bridge_pr` tool bob calls (section 6). The position is that the privilege boundary does not widen - the orchestrator already held it, and the human-in-the-loop justification is preserved because bob IS the human front-end - with hard-to-reverse tools (`spawn_bridge_pr`, `spawn_down`, anything pushing to a real remote) configured approval-required. The open piece is verifying the exact `agent.ts`/tool-level mechanism eve exposes for marking a tool approval-required versus auto-run (section 6); needs a doc check before those tools ship.

6. **eve beta churn.** The `@ai-sdk/tui`-over-durable-session wiring, the skills `load_skill`/Agent-Skills portability claim, schedules' dev-versus-prod firing, and Workflow run limits are all beta-stage concepts pulled from current docs, not stable signatures (section 11 register). Hedge: pin the exact eve version for the first-increment proof and re-validate the channel and session contracts against the changelog before any real-mission cutover.

**Recommended first build increment:** section 9 steps 1-3 combined, against a throwaway bob project - build the L1 agent (the proven leaf channel + tools, plus the new `spawn_*`/`notify_human` tools and one ported skill) and then prove the TWO claims that are genuinely new relative to the already-proven leaf: (a) the all-day human front-end rides a durable session that rehydrates on relaunch (open question #1, bet 1), and (b) the multiplex - a room frame produces a turn that `notify_human`s into a concurrently-live human session with no lost, duplicated, or raced turn (open question #2). Everything else in the RFC is either already proven at the leaf (the native channel, the connector, exactly-once, indistinguishability - bob-demo) or is straightforward local shell-wrapping (the `spawn_*` tools) and near-verbatim markdown porting (the skills). Those two proofs are the cheapest possible falsification of bob-as-L1's two new bets; if either fails, the interactive-orchestrator direction needs rework before any fleet integration is spent on it. This mirrors the eve-harness RFC's own first-increment logic (prove the core mechanic and durability in isolation before spawn.py or fleet work), advanced one layer up to the claims that a leaf never had to make.

---

## 11. Appendix

### 11.1 Beta-churn risk register

eve and AI SDK 7 are beta; each primitive this design leans on carries churn risk. For each, the hedge that keeps a breaking change small. This extends the eve-harness RFC's own register (S11.1) with the primitives bob-at-L1 newly depends on.

- **The `@ai-sdk/tui` rendering-client-over-durable-session wiring (highest churn, highest risk).** Section 4's front end reuses `@ai-sdk/tui`'s render primitives against a durable eve session rather than calling the documented `runAgentTUI({ agent })` entry point against an in-process agent - and no fetched source confirms a documented seam for that (section 4.1). The package's public contract is local/in-process/until-exit [ai-sdk-docs: terminal-ui], so the wiring this RFC needs lives at or below that contract's edge, exactly where a beta package is most likely to change. Hedge: keep bob's terminal client behind a thin adapter over eve's session-stream API (`GET /eve/v1/session/<id>/stream`, `POST /eve/v1/session`), so if `@ai-sdk/tui`'s internals shift, only the rendering layer is affected, not the durable-session contract underneath; and prove the wiring in the first increment (section 10) before building anything else human-facing on it.
- **Skills `load_skill` auto-dispatch and Agent-Skills portability.** Section 7 leans on the claim that Agent-Skills-standard markdown ports to eve "as-is" [eve-docs: skills] and on `load_skill`'s match-or-name dispatch. Both are current-doc concepts, not pinned signatures. Hedge: the ported skills are pure markdown-plus-frontmatter with the tool-call substitutions isolated (section 7.1), so a frontmatter-schema change is a small mechanical edit; verify the portability claim empirically on the first skill ported rather than trusting it wholesale.
- **Schedules dev-versus-prod firing.** Section 3.3 notes `eve start` fires schedules on cadence while `eve dev` does not, and gives `defineSchedule`'s `run`/`markdown` shapes [eve-docs: schedules]. bob does not depend on schedules in this RFC (they are a flagged future capability, section 10-adjacent), so churn here is low-impact; the hedge is simply not building on schedules until the capability is actually scoped.
- **Durable sessions / Workflows limits, at L1 multiplicity.** The whole design rests on session durability (the leaf PoC proved resume across restart and redeploy - eve-harness-v0.handoff.md S2), but bob runs the human session plus N mission sessions concurrently under one agent (sections 4.4, 5), and no fetched doc gives a concurrent-session ceiling or per-agent Workflow limits [eve-docs: concepts; eve-harness.rfc.md S11.1]. Hedge: keep turns and event logs small (the parent RFC's hedge), and treat the session-count ceiling as an open question (section 10 #3) to measure before running many concurrent missions on one bob.
- **Cross-session turn ordering.** `notify_human` posting from a mission session into the human session (section 5) assumes eve handles two concurrent turns across two sessions of one agent sanely; the docs do not specify (section 10 #2). Hedge: this is the same risk class the parent RFC already flagged for same-session frames (S10 risk 4) and carries the same mitigation - a spike in the first increment before `notify_human` is load-bearing.
- **Tool-approval config surface (orchestration-side).** Sections 6 and 10 #5 require marking `spawn_bridge_pr`/`spawn_down` approval-required; the exact `agent.ts`/tool-level mechanism is unverified in the fetched docs. Hedge: gate the hard-to-reverse tools behind the approval config the moment it is confirmed, and until then keep those tools out of any autonomous path (human-typed invocation only).
- **Incremental connector attach/detach (orchestration-side).** Section 8's live per-mission subscription attach/detach on a long-lived connector is new relative to the all-or-nothing leaf connector (section 10 #3). Hedge: it is additive to the proven per-`(room, agent)` cursor/`--since` mechanics, so it can be built and tested as an extension of the existing connector rather than a rewrite, and `spawn_status` must surface each subscription's liveness the way it already surfaces the whole connector's (inheriting the parent RFC's connector-liveness discipline, S10 risk 2).

### 11.2 Sources

eve and AI SDK (fetched current for this RFC, 2026-07 era; eve is a Vercel public beta, subject to change before GA):
- [eve-docs: overview] https://vercel.com/docs/eve
- [eve-docs: concepts] https://vercel.com/docs/eve/concepts
- [eve-docs: skills] https://eve.dev/docs/skills
- [eve-docs: schedules] https://eve.dev/docs/schedules
- [eve-docs: channels-custom] https://eve.dev/docs/channels/custom
- [eve-docs: pricing] https://vercel.com/docs/eve/pricing
- [eve-kb: add-skills] https://vercel.com/kb/guide/how-to-add-eve-skills
- [eve-blog: introducing-eve] https://vercel.com/blog/introducing-eve
- [fluid-compute-docs: default-settings-by-plan] https://vercel.com/docs/fluid-compute
- [ai-sdk-blog: ai-sdk-7] https://vercel.com/blog/ai-sdk-7
- [ai-sdk-docs: terminal-ui] https://ai-sdk.dev/docs/agents/terminal-ui

Our stack (this repo, consumed as proven givens):
- [eve-harness.rfc.md] orchestration/eve-harness.rfc.md - the design of record this RFC is the sequel to
- [eve-harness-v0.handoff.md] orchestration/eve-harness-v0.handoff.md - the leaf-worker v0 proof + wire mechanics
- [eve-harness-v0.brief.md] orchestration/eve-harness-v0.brief.md - the leaf-worker v0 constraints (no-concurrent-delivery-per-token, eve start vs eve dev)
- [bob-demo.evidence.md] orchestration/bob-demo.evidence.md - live-fleet indistinguishability proof
- [orchestration.md] .botfile/memory/tools/orchestration.md - herdr/orbal-net/spawn.py, push model, 8 event kinds
- [spawn.py] orchestration/spawn.py - fleet driver (up/down/poke/bridge-pr, connector lifecycle, commit 0d30979)
- [AGENTS.md] AGENTS.md - orchestration protocol, 3-layer membership, GitHub-bridge norm
- [scope-mission.md / spawn-team.md] .claude/commands/ - the two orchestration skills ported in section 7

Beta note: eve is a Vercel public beta (framework, APIs, and behavior may change before GA). Every eve claim above is grounded in a current doc as cited; the design is anchored to concepts, not exact signatures, so a signature change does not invalidate the architecture. Where a needed capability is NOT confirmed by a fetched doc - most sharply the `@ai-sdk/tui`-over-durable-session wiring (section 4.1) - the RFC says so explicitly and carries it as a ranked open question (section 10) rather than asserting a clean fit.
