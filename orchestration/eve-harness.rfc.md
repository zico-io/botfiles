# RFC: eve-harness - a bespoke terminal agent harness on Vercel eve

- Status: Draft (north-star architecture RFC; no shipped code)
- Owner: squad-rfc-lead (mission eve-harness)
- Date: 2026-07-09
- Scope: design and prose only. This RFC does not modify spawn.py, AGENTS.md, or orbal-net. It consumes the post-push orbal-net model as a given and takes a concrete position on each in-scope question rather than surveying options.

---

## 1. Summary and thesis

We run a 24/7 multi-agent product operation on a three-layer fleet: an L1 orchestrator, L2 leads, and L3 workers, each a terminal agent (claude, codex, or pi) placed by herdr and coordinated through a per-mission orbal-net server. The coordination is real and durable, but the harness underneath it is glue: every agent is a generic terminal chat app, and every act of coordination - joining a room, blocking for the next task, emitting a progress event, reporting a result - is a hand-written `orbal-net` CLI shell-out that the bootstrap prompt has to teach each fresh agent to perform. The fleet works because the prompt disciplines the model into calling the CLI at the right moments, not because the runtime knows what a room or a turn is.

This RFC proposes replacing that glue with a bespoke harness built on Vercel's eve framework, and it takes one defining bet:

> **orbal-net becomes a native eve channel.** A message pushed into a room over orbal-net's post-push SSE stream is delivered to the eve runtime as an inbound event, and the runtime turns it into an agent turn automatically. The agent no longer shells out to `orbal-net recv` to block for work - it receives a turn because a room message arrived - and it emits messages and the eight progress-event kinds as first-class runtime outputs (typed tools), not as memorized CLI syntax.

A second bet follows from the first. eve agents are durable backends deployed on Vercel (Functions plus Workflows), not just local processes. If a room message becomes an inbound event, then an agent deployed remotely can take turns with no terminal, no pane, and no host. This targets the single sharpest gap in today's system: herdr can wake only agents whose panes live on the host, so a remote idle agent cannot be woken (orchestration.md line 19). In the eve model there is no idle pane to wake - a durable session persisted in Vercel Workflows resumes when the next room message arrives.

One honest qualification, load-bearing enough to state in the summary: eve channels and sessions are Vercel Function-backed, and a Function has a hard `maxDuration` ceiling (800s at GA, 1800s in beta), so **the channel cannot itself hold the long-lived orbal-net SSE connection open.** The design therefore introduces a small always-on **connector**: a standalone process that holds the orbal-net stream and, on each pushed message, makes one short call into the eve session endpoint to mint or resume a turn. This does not eliminate the "something must stay alive" requirement - it **relocates** it from a full herdr-driven pane-plus-harness process on the mission host to a small, stateless, host-independent, restartable connector (all durable state lives in Workflows, not the connector). The remote-wake gap narrows sharply rather than vanishing, and this RFC says so plainly rather than overclaiming.

The prize is one codebase with two deployment targets. Run the same agent definition as an AI SDK 7 terminal UI on a laptop and it is a local agent in a herdr pane, exactly like today. Deploy it to Vercel and it is a headless remote backend that holds a mission seat over the network, reachable only through orbal-net and the Vercel dashboard. The orchestration model - three layers, room membership, consuming versus non-consuming reads, the eight event kinds - is preserved unchanged; only the substrate under it changes from "generic terminal app plus CLI glue" to "a purpose-built runtime that speaks orbal-net natively."

This document is a north-star: an RFC a lead could turn straight into a build mission. eve is a Vercel beta; every claim about it is grounded in current docs (cited inline, consolidated in the appendix) and every beta-churn risk is called out.

---

## 2. Background: the workflow we run today

A reader who knows neither eve nor our stack needs this section; the rest of the RFC builds on it.

### 2.1 The three-layer fleet

Multi-agent work runs as a **mission**. A mission has a fixed hierarchy capped at three layers, enforced by room membership (AGENTS.md orchestration protocol; orchestration.md line 10):

- **L1 orchestrator** - the human-adjacent pane. It sets the mission brief and talks to leads. It never shares a room with a worker.
- **L2 leads** - one per feature area. Each lead is in the shared `mission-<feature>` room with the orchestrator and owns its own `squad-<lead>` room.
- **L3 workers** - the leaves. Each worker is in exactly one `squad-<lead>` room with its lead. Workers never spawn other agents.

Rooms are public and joined by name. The membership rule is the enforcement mechanism: because the orchestrator and workers never co-inhabit a room, the orchestrator structurally cannot message a worker directly, and the three-layer shape holds without a separate policy engine.

### 2.2 The two subsystems: herdr and orbal-net

Two subsystems, cleanly split (orchestration.md line 3):

- **herdr** does **placement and process**: it owns terminal panes and tabs (leads are tabs, workers are splits inside their lead's tab), launches each harness process, and runs the status line. herdr is where an agent physically lives.
- **orbal-net** does **coordination**: rooms, direct messages, agent status, and typed progress events. It is one Rust binary (github.com/zico-io/orbal-net); `orbal-net serve` is the per-mission server and every other subcommand is a client (orchestration.md lines 3-9). One server runs per mission, started by `spawn.py up`, Bearer-token authed, state in SQLite. Killing the server at teardown is the room cleanup (orchestration.md line 11).

Agent identity is the `ORBAL_NET_AGENT` env var, injected per `container exec` alongside `ORBAL_NET_URL` and `ORBAL_NET_TOKEN` by `sandbox_wrap` (orchestration.md line 14). Because `orbal-net` is a plain binary on PATH, any harness with a shell can coordinate - there is no per-harness MCP bridge. This is exactly the glue this RFC targets: coordination is available to any shell, but only because a prompt tells the model to type the commands.

### 2.3 The post-push coordination model (the baseline this RFC is written against)

This RFC is sequenced after mission-orbal-net-push. Its baseline is the **post-push** model (orchestration.md lines 16-19), not today's poll/wait path:

- **Push, not poll.** `orbal-net recv <room>` is an SSE-backed blocking read over one persistent `POST /stream` connection. The server pushes the instant a message lands (pure notify, no poll loop) then closes the connection. It replaces the old long-poll `wait`. Agents BLOCK on `recv`; shell poll loops (`while`/`for`/`sleep` around orbal-net) are forbidden - those loops starved the first real mission (orchestration.md line 16). `--follow` keeps the connection open as a live non-consuming tail; `--since <msgSeq>:<evtSeq>` resumes a dropped connection exactly.
- **Consuming versus non-consuming.** `read` and `recv` (without `--follow`) are **consuming**: each advances the caller's per-room cursor, so a second call returns only newer messages. `peek`, `events`, and `recv --follow` are **non-consuming**: they never advance the cursor, so monitoring a room never eats a message an agent still needs (orchestration.md line 17). Monitoring a room with `read` once silently consumed the orchestrator's own view and looked like state loss; that footgun is why `peek` exists.
- **Typed progress events.** Agents emit typed progress with `orbal-net event <room> <kind>` and the `orbal-net progress <room> N/M` shorthand. There are exactly eight kinds: **task-start, task-done, task-error, task-abort, step, phase, blocked, handoff** (orchestration.md lines 18-19). Events live in a separate SQLite table with no cursor concept, so they are monitor-safe by construction, and the write path pushes each event to monitor-mode `/stream` subscribers. `orbal-net tui` renders the fleet live from this stream - a room-thread drill-in plus a per-agent progress panel - over one persistent server-push connection.

Note on today's binary: the installed `orbal-net` in this mission still exposes `wait`, not `recv`. That is a binary-version lag used only for coordinating this doc mission; the RFC is written against the `recv`/SSE model per AGENTS.md and orchestration.md, which is the design of record.

### 2.4 spawn.py: standing a fleet up and down

`orchestration/spawn.py` is the fleet driver (orchestration.md lines 11-14):

- `up <roster.json> [teams]` starts the mission's orbal-net server, spawns the panes (leads as tabs, workers as splits), launches each harness, and injects a **bootstrap** prompt per role that runs `orbal-net join`/`create-room`/`send` and then tells the agent to block on `recv`. A roster is a catalog of teams; `up`'s optional team list spawns only the teams a mission needs. `up` is transactional - any failure tears down the partial VM/workspace/server.
- `poke <feature> <role>` wakes an **idle** agent (one not currently blocked on `recv`) via a herdr pane-run nudge. It is not an orbal-net message, so it does not breach room hierarchy. Crucially, `poke` can only reach panes on the host (orchestration.md line 19) - this is the remote-wake gap.
- `down <feature>` SIGTERMs the orbal-net server (all rooms vanish) and closes the workspace.
- `bridge-pr <feature> [title]` harvests the mission branch into the origin repo, pushes it, and opens the PR via `gh`. Spawned agents have no `gh` and no network and their clone's origin is a local mirror, so the orchestrator bridges every live GitHub step; agents only prepare files and text (spawn.py lines 166-183; AGENTS.md).

### 2.5 The gap this RFC exists to close

herdr's `poke` is a host-only pane nudge. The orbal-net server is network-reachable, so a remote container can **coordinate** - it can join rooms and send messages. But **waking** a remote idle agent is out of scope today, because herdr cannot reach a remote pane (orchestration.md line 19). The remote-agent story is therefore half-built: remote agents can talk but cannot be summoned. This is the exact seam the eve bet targets. If the inbound push is what creates a turn, the pane-based wake mechanism is no longer needed, and "remote" stops being a special case.

---

## 3. What eve is - a primer on its primitives

eve is Vercel's filesystem-first framework for durable backend AI agents [eve-docs: overview]. You author an agent as files under an `agent/` directory; eve discovers them, compiles a manifest, and serves the result as a deployable app running on Vercel Functions [eve-docs: concepts]. It is public beta as of 2026-06-19 and "subject to change" before GA [eve-docs: overview] - treat every primitive below as beta-stage, not stable API.

The motivating problem, in Vercel's own framing: "Agents today are where the web was before frameworks, with everyone hand-rolling the same plumbing and nothing carrying over to the next one" [eve-blog: introducing-eve]. eve's answer is the move Next.js made for the web: convention over hand-rolled infrastructure. That is precisely our situation - our "plumbing" is the orbal-net bootstrap prompt re-taught to every fresh agent.

### 3.1 Primitives (one per file or directory under `agent/`)

- **instructions.md** - the always-on system prompt, put in front of every model call. Required; the only required file [eve-docs: concepts].
- **agent.ts** - runtime config via `defineAgent({ model: ... })`. Model strings resolve through AI Gateway, so a deployed agent authenticates with Vercel OIDC instead of managing provider keys directly [eve-docs: concepts].
- **tools/*.ts** - one typed tool per file; the filename becomes the tool name the model sees, with no registration step [eve-docs: concepts].
- **skills/*** - markdown playbooks loaded only when relevant, so multi-step procedures do not bloat the always-on prompt [eve-docs: concepts].
- **subagents/*** - child agents the model delegates focused subtasks to. Two flavors: the built-in `agent` tool (a fresh-context copy of the current agent, sharing its sandbox and tools, supporting parallel fan-out) and declared subagents under `agent/subagents/<id>/` (their own instructions/tools/skills/sandbox, invoked with a `message` field since the child never sees the parent's conversation history, returning structured output when an `outputSchema` is set) [eve-kb: subagents].
- **channels/*** - platform entry points (HTTP is on by default; Slack, Discord, Teams, Telegram, Twilio, GitHub, Linear ship as adapters). A channel is "just a small adapter file" that translates an inbound platform event (webhook, message, HTTP call) into a structured request against the agent's session API. It does not push events into the agent on its own initiative [eve-blog: introducing-eve][eve-docs: concepts].
- **connections/*** - typed integrations with external services, keeping provider config and credentials out of the prompt and tool code; pairs with Vercel Connect for delegated OAuth [eve-docs: concepts].
- **sandbox/*** - the agent's one isolated bash-style compute environment; framework tools (`bash`, `read_file`, `write_file`) and authored tools target it. On Vercel it can run on Vercel Sandbox (ephemeral microVMs) for untrusted or model-generated commands [eve-docs: concepts].
- **schedules/*** - cron-triggered handlers that start a turn on their own clock, e.g. an autonomous agent that "works every new lead the moment it comes in" [eve-blog: introducing-eve][eve-github: readme].

### 3.2 Sessions and turns (the durability core)

A **session** is the durable conversation or task created by a channel or HTTP call; each user message or external event inside it is a **turn**. During a turn the agent can call tools, load skills, touch the sandbox, delegate to subagents, and stream lifecycle events back to the client [eve-docs: concepts]. Concretely:

```
POST /eve/v1/session {"message": "..."}   -> 201, x-eve-session-id header, continuationToken
GET  /eve/v1/session/<id>/stream          -> NDJSON stream of lifecycle events
```

Sessions run on top of **Vercel Workflows**: workflows persist progress as an event log and deterministically replay it, so a session "can survive cold starts, redeploys, and long pauses while it waits for the next message or a tool result" [eve-docs: concepts]. This is the load-bearing fact for this RFC - durability is a property of the session/turn substrate, not of any one channel. Critically, a Workflow gets unlimited *lifetime* by **pausing** between turns (no live process or socket held), not by keeping a connection open across that span [fluid-compute-docs: default-settings-by-plan]; section 5 and section 6 depend on that distinction.

### 3.3 AI SDK 7 terminal UI

Separately from eve, AI SDK 7 ships `@ai-sdk/tui`: `runAgentTUI({ agent })` opens an interactive local terminal session against a `ToolLoopAgent` - prompt input, streamed markdown, tool cards, reasoning display, and tool-approval prompts, all in-process [ai-sdk-blog: ai-sdk-7]. It is explicitly local dev/demo, not a deployed channel: it "connects directly to an agent instance for immediate local development and testing, not designed for remote deployment" [ai-sdk-blog: ai-sdk-7]. The durable, remote-survivable counterpart is `@ai-sdk/workflow`'s `WorkflowAgent`, built for "durable, resumable agent execution that survives process restarts, deploys, interruptions, and delayed approvals" [ai-sdk-blog: ai-sdk-7] - the same substrate eve's sessions build on.

---

## 4. Mapping: eve primitive -> our orchestration model

| eve primitive | what it is (1 line, cited) | our analog today | fit | our position |
|---|---|---|---|---|
| instructions.md | Always-on system prompt in front of every model call [eve-docs: concepts] | spawn.py's per-role `bootstrap()` prompt string plus AGENTS.md loaded by the harness | clean | Adopt instructions.md as the durable equivalent of our bootstrap string; AGENTS.md content folds in almost verbatim. |
| tools/*.ts | One typed, model-callable function per file, schema-validated, no registration [eve-docs: concepts] | orbal-net/herdr CLIs invoked via shell (Bash), driven by memorized command syntax in prose instructions | stretch | Wrap orbal-net ops (join/send/recv/event/progress) as typed eve tools; removes shell-quoting/argv bugs and gives the model a validated call surface instead of memorized CLI syntax. |
| skills/* | Markdown playbooks loaded on demand, kept out of the always-on prompt [eve-docs: concepts] | `.claude/commands/*.md` plus `.botfile/memory/tools/*.md`, loaded by the harness's own skill system | clean concept / stretch mechanics | Our skill content (spawn-team.md, orchestration.md) ports almost directly to eve's skills/ format; one of the easiest primitives to migrate. |
| subagents/* | In-process child-agent delegation: fresh context, same runtime, tool-call semantics, optional structured output [eve-kb: subagents] | herdr-spawned lead/worker panes: separate OS processes and harness instances coordinated over orbal-net rooms | gap | Do not replace the multi-process fleet with in-process subagents; they solve different problems (subagents = cheap fan-out within one turn; our fleet = independently-running, differently-harnessed, long-lived processes). Use eve subagents for sub-tasks *within* a layer, never *as* a layer; keep orbal-net rooms for cross-process coordination. |
| channels/* | Small adapter file translating an inbound platform event into a session-API call [eve-blog: introducing-eve] | spawn.py's bootstrap-and-poke: a host-side herdr PTY nudge, not a message-channel abstraction | stretch | Build the orbal-net channel plus an external connector (section 5): the connector holds the orbal-net SSE open and forwards each pushed message into a session/turn call. Model it as "channel fed by a long-lived external connector," not "webhook receiver" and not "channel that holds a socket." |
| connections/* | Typed integration with an external service, credentials kept out of prompt and tool code, pairs with Vercel Connect [eve-docs: concepts] | `mission_secrets()` file-copy of claude/codex creds into a per-mission dir plus ORBAL_NET_URL/TOKEN env injection | stretch | Low priority for the first increment; ad hoc file-copy is adequate for local-VM missions. Revisit only when agents run as deployed eve backends where Connect's OAuth management starts to matter. |
| sandbox/* | The agent's one isolated bash-style compute environment, optionally Vercel Sandbox microVMs [eve-docs: concepts] | one shared Apple `container` microVM per MISSION (8 CPU/12GB, full Rust toolchain), bind-mounted to all agents in the fleet | stretch | Conceptually identical (isolated compute for agent-driven commands) but cardinality differs: ours is one-per-mission, eve's is one-per-agent. A deployed eve role's sandbox needs to mount the same isolated mission-branch clone; eve's sandbox does not dictate repo layout. See section 10 risk #1. |
| durable sessions + turns (Vercel Workflows) | Event-log-backed conversation state that survives cold starts, redeploys, and long pauses [eve-docs: concepts] | none - state lives in the harness's live context plus whatever got committed to git; a dead pane or container loses everything uncommitted | gap | The gap we most want to close. A lead/worker built as an eve agent behind the orbal-net channel survives being idle between room messages the same way a Vercel Function survives between requests - see section 6. |
| AI SDK 7 terminal-UI pkg (@ai-sdk/tui) | `runAgentTUI({ agent })`: local-only interactive terminal session against a running agent [ai-sdk-blog: ai-sdk-7] | herdr pane running a claude/codex/pi TUI: a live, human-watchable terminal session | clean but scope-limited | Keep herdr plus harness TUIs for local/interactive work exactly as today. `@ai-sdk/tui` is not a replacement for anything we have; it is eve's version of "attach a terminal for a human to watch," same job, same locality constraint. |

---

## 5. Native channel design: orbal-net SSE frame -> eve turn

**Position:** orbal-net becomes a custom eve channel (`agent/channels/orbal-net.ts`, `defineChannel` from `eve/channels` [eve-docs: channels-custom]), fed by a small external **connector** process - not by the channel holding the SSE connection itself. A channel is Function-backed and would die at the `maxDuration` ceiling (section 6.3), so it cannot listen indefinitely. Instead the channel is webhook-style: a short `POST /orbal-net/message` route that takes one already-arrived frame and turns it into a turn, the same shape as eve's stock Slack/Discord adapters. The connector plays the always-open role that Slack's own infrastructure plays for a Slack channel; orbal-net has no outbound webhook delivery of its own (only an inbound-attach SSE stream), so it needs its own small holder to play that role.

**One connector per mission.** The connector is a sibling of the orbal-net server: one per mission, holding one `orbal-net recv <room> --follow` subscription per (room, agent) pair it serves, multiplexing every deployed role's rooms, and routing each pushed frame's POST to whichever deployed role's webhook owns that agent identity. One restartable, superviseable process beats N per-agent processes for the same operational reason the mission already centralizes on one orbal-net server rather than one per room.

**Contract mapping:**

- One eve agent = one orbal-net agent identity. A lead needs frames from 2 rooms (`mission-<feature>`, `squad-<lead>`), a worker from 1 (`squad-<parent>`) - unchanged room-membership rule [AGENTS.md orchestration protocol].
- The connector is the sole owner of each (room, agent) pair's read cursor. Consuming semantics stay exactly where they are today (recv/read advance the cursor; peek/events/`--follow` do not) - just relocated from "inside the agent process" to "inside the connector process." The connector holds `recv --follow` (non-consuming) for the live tail and owns the authoritative cursor via its `--since` bookkeeping, so an auto-turn on a pushed message never silently clobbers the cursor contract: exactly one component advances the cursor, and it is the connector, deterministically.
- On each pushed frame the connector makes one short HTTP POST to the deployed channel's webhook with `{room, agent, text, msgSeq, evtSeq}`. The channel handler calls `send(text, { auth: null, continuationToken })` with `continuationToken = <room>:<agent>` [eve-docs: channels-custom]. This gives each (agent, room) pair its own durable session/turn chain, matching orbal-net's per-room per-agent cursor 1:1 - the token is the resume handle, the same role `--since <msgSeq>:<evtSeq>` plays for orbal-net [orchestration.md]. The turn is created by a short Function invocation, well under `maxDuration`, not a long-held one.
- Outbound (replies and progress) is not modeled as channel delivery. The model gets tools that map 1:1 to today's CLI surface - `orbal_net_send`, `orbal_net_event`, `orbal_net_progress`, `wcommit` - each a thin POST straight to the mission's orbal-net server (mirroring `orbal_net_post` in spawn.py). Only the inbound path needs a held-open socket; the reply path does not round-trip through the connector. Keeping replies as model-invoked tools rather than channel-side auto-reply preserves today's behavior that an agent chooses *when* to speak: an agent may take many turns and tool calls before it has something to report, which channel-side auto-reply-on-turn-completion would not respect. The eight event kinds (task-start/done/error/abort, step, phase, blocked, handoff) are emitted natively as `orbal_net_event` tool calls from the runtime, no CLI shell-out.
- Reconnect: the connector persists its last-seen `msgSeq:evtSeq` per (room, agent) and resumes the SSE connection with `--since` on drop. A Vercel Function recycle or redeploy loses nothing (session state lives in eve's Workflow store); a connector restart loses nothing either (only the resume cursor needs re-establishing, which `--since` does exactly).

**Sequence sketch** (one room, one agent):

```
orbal-net server        connector (host process,       eve channel               eve session/turn
                         NOT a Vercel Function)         (Function, webhook)
  |-- SSE push -------------->|                              |                        |
  |   (msg lands in room)     |-- short POST /orbal-net/message ------------------->  |
  |                           |   {room, agent, text, msgSeq}  |-- send(text, token) ->|
  |                           |                              |                        |--- turn runs, calls tools
  |<---------------------------------------- orbal_net_event(room, phase, ...) -------|
  |<---------------------------------------- orbal_net_send(room, result) ------------|
  |                           |                              |    <-- turn completes (Function returns)
  |                           | (connector's cursor advances; reconnects with --since on drop)
```

This is a straight re-implementation of the bootstrap-prompt protocol every claude/codex/pi agent follows today [spawn.py `bootstrap()`]. The difference is that the loop (`recv` -> act -> `send`/`event` -> `recv`) is compiled into the connector, channel, and tools once, instead of re-taught to a fresh model context every mission via a chat prompt.

---

## 6. Remote agents and deploy-as-backend: how the remote-wake gap closes

### 6.1 The gap, precisely stated

herdr does placement and process for a pane on the *local* host; `poke` is a `herdr pane run` PTY nudge for an agent sitting idle - one not currently blocked on `recv` (orchestration.md; spawn.py `poke()`). herdr cannot reach a pane on a remote machine at all, so a remote container can *coordinate* via orbal-net (the server is network-reachable, `ORBAL_NET_ADVERTISE_HOST` covers ingress) but cannot be *woken* if it goes idle - it depends on already being alive and blocked on `recv` (orchestration.md: "waking a remote idle agent... is out of scope").

### 6.2 Position: eve closes this by removing the idle-pane concept, not by building a remote poke

A deployed eve agent has no PTY and no pane to wake. It is a durable session persisted via Vercel Workflows and replayed to reconstruct state [eve-docs: concepts], running from Vercel Functions with Fluid Compute for the streaming turn [eve-docs: overview]. There is nothing analogous to "idle but not blocked on recv": the turn is created by a `send()` call into the session endpoint, so the arrival of work and the wake are the same event, not a message a separately-alive process has to notice. This satisfies the same ingress precondition already documented for remote coordination (the deployed app must reach the mission's advertised `orbal_net_url`) [orchestration.md] with no new networking primitive. What is new is that Vercel, not herdr, owns process placement and lifecycle for these agents.

### 6.3 The honest caveat: the gap narrows, it does not vanish

eve's answer is not "a way to wake a remote pane" - it is "make the agent not need waking." But something must still hold the orbal-net SSE connection open, because (as section 5 establishes) the Function-backed channel/session cannot. That something is the connector. So the always-on requirement is **relocated**, not removed: instead of a full herdr-driven pane-plus-harness process staying alive on the mission host, a small stateless connector (hold-SSE, POST-on-message) stays alive somewhere with network reach to both the orbal-net server and the deployed eve endpoint. It is much lighter, host-independent, and itself restartable without losing session state (state lives in Workflows, not the connector). The accurate claim for this RFC is not "no liveness requirement at all" - it is "a much lighter, relocatable one."

The load-bearing fact behind this: channel webhooks, session requests, stream attachments, and tool execution are all served by Vercel Functions [eve-docs: pricing], which carry a hard `maxDuration` ceiling (300s Hobby, 800s Pro/Enterprise GA, 1800s beta extended) [fluid-compute-docs: default-settings-by-plan]. The docs redirect unbounded lifetime explicitly: "For workloads that require unlimited execution time, use Vercel Workflows, which allow your code to pause, resume, and maintain state for minutes to months without duration limits" [fluid-compute-docs: default-settings-by-plan]. That "months" is elapsed time between paused turns, not a live socket held for months. A held orbal-net `recv --follow` connection would hit the Function ceiling far short of "listen indefinitely," which is why the connector lives outside the Function boundary.

There is a second, genuinely positive consequence worth stating plainly: the connector design **inverts the network direction** of the remote case. Today, reaching a *remote* container requires *inbound* routing to it - the container must be able to route to the host's advertised `orbal_net_url` (firewall, NAT, VPN), which `ORBAL_NET_ADVERTISE_HOST` exists to configure (orchestration.md). With the connector, the connector runs on the mission host next to `orbal-net serve` (trusted, already holds the token) and makes an *outbound* HTTPS call to the deployed eve app's public endpoint. No inbound routing to any remote agent is needed. The remote-wake gap does not just narrow; its direction flips from "the host must reach into the remote agent" to "the host calls out to it," which is the strictly easier network problem.

### 6.4 Local-TUI versus remote-backend duality

eve ships `eve dev` for local interactive work, and AI SDK 7's `@ai-sdk/tui` (`runAgentTUI`) runs an agent in an interactive terminal for local dev and demos [ai-sdk-blog: ai-sdk-7][ai-sdk-docs: terminal-ui]. That local mode is the direct drop-in analog of today's claude/codex/pi-in-a-herdr-pane - same PTY-in-a-pane shape, so herdr keeps working unchanged for any role still run this way, and it requires a reachable local pane. The *deployed* eve app (same `agent/` project, `vercel deploy`) is headless and backend-only, addressable purely through its channels (orbal-net) plus the Vercel dashboard and Agent Runs for observability [eve-docs: concepts]. A fleet can be mixed: some roles local-TUI (herdr-placed, human-watchable, identical to today), others deployed-backend (Vercel-placed, reachable only via orbal-net plus dashboard). This duality is what section 9's migration path leans on: convert one role at a time, with herdr and the non-converted roles not needing to know the difference.

---

## 7. Three-layer and room-membership mapping onto eve

**Position: each L2 lead and each L3 worker stays a distinct eve agent (its own deployment, its own orbal-net identity, its own channel subscription), not an eve subagent nested under its parent.** eve subagents run with fresh conversation history, separate from the parent's session and invisible to anything outside that turn; a declared subagent has no independent identity or channel of its own [eve-docs: subagents: "it never sees the parent's history"]. If a worker were modeled as a lead's subagent it would have no `ORBAL_NET_AGENT`, no room membership, and no cursor, so `orbal-net peek`, `events`, and the `tui` progress panel would have nothing to show for it - silently breaking today's per-agent monitoring (orchestration.md: "Live dashboard" / "Progress events"). Keeping every role a first-class eve agent with its own orbal-net-channel subscription preserves the room model exactly as documented: L1-L2 share `mission-<feature>`, L2-L3 share `squad-<lead>`, L1 never shares a room with L3 [AGENTS.md orchestration protocol]. Room membership continues to be the sole hierarchy-enforcement mechanism, the same property `spawn.py validate()` checks today.

**Where eve subagents and the built-in `agent` tool DO fit:** intra-agent fan-out that never needs orbal-net visibility - a worker fanning out several declared or built-in subagent calls to read different files in parallel within one turn [eve-docs: subagents]. This is a compute-topology concept, not a room-membership one, so it does not count against the three-layer cap - the cap is defined by room membership, not process nesting. Section 4's `subagents/*` row records this position: usable *within* a layer, never *as* a layer.

**Where membership enforcement lives:** unchanged, in orbal-net, not the harness. The server owns room membership and the per-room cursor; the eve harness is just another client subscribing to rooms it is entitled to. This keeps a single source of truth for the hierarchy and means a mixed fleet (some eve, some legacy) enforces the same rule the same way. The harness must not re-implement or second-guess membership; it subscribes to the rooms its identity belongs to and no others.

**Session cardinality:** a lead runs two concurrent durable sessions (one per room, keyed by the `<room>:<agent>` continuation token from section 5); a worker runs one. This falls directly out of eve's per-continuationToken session model [eve-docs: channels-custom] - no new eve primitive is needed to represent "an agent in two rooms."

---

## 8. herdr's role and what spawn.py changes

**herdr's role shrinks; it does not disappear.** It stays the process and placement layer for (a) the orchestrator's own pane (explicitly out of scope for conversion - "the pane you are already in," never spawned by spawn.py) and (b) any lead/worker deliberately run in local `eve dev` / `@ai-sdk/tui` mode during migration or debugging (section 6's local-TUI duality). It has no role for a deployed eve agent - no pane exists to place.

**spawn.py changes, concretely:**

- **The connector is a new always-on operational dependency that spawn.py must own.** A new `orbal_net_connector_up(feature)`, symmetric to `orbal_net_up()`, starts one connector process per mission right after the server (detached, `start_new_session`, logged to `orbal-net-connector.log`, pid recorded in `mission.json` - the same pattern as the server), subscribing on behalf of every deployed (non-herdr) role's rooms. `down()` SIGTERMs it alongside the orbal-net server. Per worker-eve's recommendation this connector should be prototyped as the smallest possible standalone process (not a Vercel Function) before any deployed role goes past a proof-of-concept: it is the one genuinely new always-on dependency this RFC introduces, and it should be sized and tested in isolation first. `spawn.py status()` must report connector liveness the same way it reports server liveness (section 10 risk #2), or a dead connector becomes a silent stall.
- `HARNESSES` gains no simple `"eve"` entry in the existing sense, because the existing entries are all "shell command that becomes a herdr pane." A deployed eve role instead needs a *deploy* path (`vercel deploy` per agent project) that `up()` calls alongside, not instead of, the herdr/container path used for local roles. `up()`'s per-role branch becomes: local role -> today's `launch()` (herdr pane plus bootstrap injection); deployed role -> a new `deploy_eve_role()` that ships the agent project and does not touch herdr.
- `bootstrap()` - the prompt that teaches a fresh model context to join a room, block on `recv`, and emit events - is not needed for deployed roles. That protocol is compiled once into `agent/channels/orbal-net.ts` plus `agent/tools/orbal_net_*.ts` (section 5) and reused by every mission, rather than re-typed into every agent's first turn. `bootstrap()` remains unchanged and necessary for any role still running local-TUI.
- `orbal_net_up()`, room creation, and the brief-seeding flow are unchanged - a deployed eve role is still just another orbal-net client hitting the same per-mission server; nothing about server lifecycle changes.
- `poke()` becomes unnecessary for deployed roles (section 6: no idle-pane failure mode) but is still required for local-TUI roles, so it is scoped down to "local roles only," not removed.
- `validate()`'s three-layer and room enforcement is untouched - it is a property of the roster and room graph, independent of which roles are local versus deployed (section 7).
- `down()` needs a new branch for deployed roles: no container or pane to tear down, but the Vercel deployment must be removed or scaled to zero and its mission-scoped `ORBAL_NET_TOKEN`/`ORBAL_NET_URL` env vars revoked.
- The `MISSIONS_ROOT` / mission-clone-per-feature model is host and container local and does not extend to a deployed eve role's Vercel Sandbox - the write-back gap flagged as risk #1 in section 10, which gates how much of `wcommit`/harvest can be reused as-is.

---

## 9. Migration and replacement path

An ordered path from claude/codex/pi plus CLI-glue to the eve harness, designed so spawn.py follows proof rather than leading it.

1. **Prove the core mechanic in isolation, connector included.** Build the connector as the smallest possible standalone process (per worker-eve), a webhook-style `agent/channels/orbal-net.ts`, and the `orbal_net_send`/`orbal_net_event` tools against a throwaway single-agent eve project pointed at a real (disposable) orbal-net server. No herdr, no spawn.py, no roster. Success = a message sent into a room produces a turn (via connector -> webhook -> `send()`), and the turn's tool calls land back in the room, matching section 5's sequence sketch.
2. **Prove durability.** Redeploy the same throwaway project mid-conversation (simulating a Vercel cold start/redeploy) and confirm the session resumes from the `<room>:<agent>` continuation token with no lost or duplicated frames. This is the concrete test of the "durable sessions" claim this RFC's thesis leans on [eve-docs: concepts].
3. **Convert exactly one leaf worker role.** Leaf, not lead: no children, no `bridge-pr`/`gh` dependency, smallest blast radius. Run it side by side with the rest of a real fleet still on claude/codex/pi in the same squad room. Success = `orbal-net tui`/`peek` cannot tell the eve worker apart from a claude worker in the room thread or progress panel (section 7's position depends on this holding).
4. **Resolve the sandbox/write-back gap** (section 8; section 10 risk #1) for that one worker before converting any more - either a shared-clone bridge or a direct-push model, chosen and load-bearing before step 5.
5. **Convert one lead role,** exercising the two-concurrent-sessions pattern (section 7) and confirming intra-turn subagent fan-out (section 7's "within a layer" position) works for that lead's own parallel work.
6. **Add the deploy path to spawn.py** (`deploy_eve_role()`, the `down()` counterpart, connector lifecycle - section 8) only once steps 3-5 have demonstrated parity on a real mission, not before. spawn.py should follow proof, not lead it.
7. **Orchestrator stays out of scope** for the foreseeable future - it is explicitly the human-facing pane today, and nothing in this RFC's thesis requires converting it.

Coexistence is the property that makes this safe: because room membership and the wire protocol are unchanged (section 7), a single eve agent in a room is indistinguishable to its peers from a legacy agent, so any prefix of this sequence is a shippable, mixed-fleet state rather than a big-bang cutover.

---

## 10. Ranked open questions and risks, and the recommended first increment

Ranked highest-risk first.

1. **Sandbox / git write-back gap.** A deployed eve agent's sandbox is a Vercel Sandbox microVM [eve-docs: concepts], not the shared host-mounted mission clone that `wcommit` writes into and `harvest()` fetches from today. No path in the fetched docs describes bind-mounting a host directory into a Vercel Sandbox. Until this is resolved (a shared-clone bridge, or eve agents pushing to a real git remote directly - notably a deployed eve agent likely *does* have outbound network, unlike today's deliberately air-gapped mission VM, itself a property worth re-examining rather than assuming away), no worker role can be converted past a proof-of-concept.
2. **The connector is a new always-on host dependency, and its failure is silent.** It is smaller and more restartable than a full herdr pane (no session state lives in it - sections 5 and 6), but it is still a process that must be supervised, logged, and restarted like `orbal-net serve` itself. Unlike the server, a dead connector fails silently: rooms and messages keep working, deployed agents simply stop receiving frames until someone notices. It must reconnect with `--since <msgSeq>:<evtSeq>` so a restart replays no frames and drops none (orchestration.md), and `spawn.py status()` must report connector liveness the same way it already reports server liveness [spawn.py `status()`], or this becomes an easy-to-miss stall. It must be designed for crash-restart from day one.
3. **Concurrency and cost of the connector plus many sessions.** The connector holds one long-lived SSE subscription per (room, agent) pair (a lead needs two rooms, a worker one), and each pushed frame spins a Function-backed turn. Fluid Compute is designed for this shape [eve-docs: overview], but the fetched docs do not give concrete concurrency ceilings or per-connection cost. `/docs/eve/pricing` details should be pulled before step 6 of section 9.
4. **Ordering guarantee under concurrent frames.** If two messages land in the same room while a turn for that `continuationToken` is still running, does eve queue the second `send()` behind the first or race two turns? orbal-net itself guarantees per-room `seq` ordering [orchestration.md], but that only matters if eve preserves it turn-side. Needs a spike (step 1 of section 9 is the natural place) before it is treated as safe.
5. **Token and secret delivery to a deployed agent.** The channel examples fetched all show `auth: null` [eve-docs: channels-custom]; our server requires a Bearer token minted fresh per mission [spawn.py `orbal_net_up()`]. Getting `ORBAL_NET_URL`/`ORBAL_NET_TOKEN` into a deployed role's environment per mission (a Vercel env-var write as part of `up()`, or a Vercel Connect-managed credential) is unspecified design work, called out in section 8 but not resolved there.
6. **Beta churn.** eve and AI SDK 7's terminal-UI package are both beta or new [eve-docs: overview]. Pin the exact eve version used for the step-1/2 proof-of-concept and re-validate the channel contract (section 5) against the changelog before any real-mission cutover. See the appendix beta-risk register.

**Recommended first build increment:** section 9 steps 1 and 2 combined - the throwaway single-agent proof of SSE-frame-to-turn (through the external connector) plus durability. It is the cheapest possible test of this RFC's core thesis (orbal-net-as-native-eve-channel; the push-through-connector is the wake) and it produces a concrete falsification point before any spawn.py, sandbox, or fleet-integration work is spent. Three things must all hold for the thesis to survive contact: a pushed room frame reliably mints a turn through the connector; a mid-conversation redeploy of the eve app resumes the session with no lost or duplicated frames; and a deliberate restart of the connector itself mid-conversation (not just the eve app) resumes from `--since` with no lost or duplicated frames. The connector-restart test is the one worker-eve flagged as the load-bearing unknown - it is where "the durable session survives, but does the thing holding its inbound connection survive too" gets answered. If any of the three fails, the RFC's direction is wrong and we have spent one throwaway project to learn it.

---

## 11. Appendix

### 11.1 Beta-risk register

eve and AI SDK 7 are beta; each primitive the design leans on carries churn risk. For each, the hedge that keeps a breaking change small.

- **Channels.** The channel HTTP/adapter contract is explicitly "subject to change" before GA [eve-docs: overview]. Hedge: keep the orbal-net connector behind a thin one-file translation boundary (SSE frame -> current channel call shape), so a breaking channel-API change is a small diff, not a rewrite.
- **Subagents.** The in-process delegation contract (message/outputSchema semantics) is new and likely to shift. Hedge: never route cross-process fleet coordination through subagents (section 4's gap verdict), so churn here cannot touch the orbal-net-based coordination layer.
- **Durable sessions / Workflows.** The primitive the whole remote-wake story leans on; Workflow run limits (event count, payload size, replay duration) are still-evolving beta limits [eve-docs: pricing]. Hedge: prototype one lead's session under real fleet-length turn counts before committing the migration path, and keep turns and event logs small to stay well under any ceiling.
- **AI Gateway / Vercel OIDC.** Model resolution and auth are Vercel-account-bound, a dependency our current model-provider-key setup does not have. Hedge: keep `agent.ts` model config swappable and do not require Gateway/OIDC beyond the pilot deployment, so a bare/local mode stays available if Gateway becomes a blocker.

### 11.2 Sources

eve and AI SDK:
- [eve-docs: overview] https://vercel.com/docs/eve
- [eve-docs: concepts] https://vercel.com/docs/eve/concepts
- [eve-docs: channels-overview] https://eve.dev/docs/channels/overview
- [eve-docs: channels-custom] https://eve.dev/docs/channels/custom
- [eve-docs: subagents] https://eve.dev/docs/subagents
- [eve-kb: subagents] https://vercel.com/kb/guide/how-to-use-eve-subagents
- [eve-docs: pricing] https://vercel.com/docs/eve/pricing
- [eve-blog: introducing-eve] https://vercel.com/blog/introducing-eve
- [eve-github: readme] https://github.com/vercel/eve/blob/main/README.md
- [fluid-compute-docs: default-settings-by-plan] https://vercel.com/docs/fluid-compute
- [ai-sdk-blog: ai-sdk-7] https://vercel.com/blog/ai-sdk-7
- [ai-sdk-docs: terminal-ui] https://ai-sdk.dev/docs/agents/terminal-ui

Our stack (this repo):
- [spawn.py] orchestration/spawn.py
- [orchestration.md] .botfile/memory/tools/orchestration.md
- [AGENTS.md orchestration protocol] AGENTS.md

Beta note: eve is a Vercel public beta (framework, APIs, and behavior may change before GA). Every eve claim above is grounded in a current doc as cited; the design is anchored to concepts, not exact signatures, so that a signature change does not invalidate the architecture.
