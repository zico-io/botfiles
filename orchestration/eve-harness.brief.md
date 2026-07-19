# Mission brief: eve-harness

Long name: "a custom terminal agent harness built on vercel's eve framework. first-class integration with herdr and orbal-net. brainstorm and daydream after immersing yourself in our orbal-net botfiles herdr workflow that exists today"

## Goal
Produce a north-star architecture RFC (a written design doc, NO shipped code) for a
bespoke terminal agent harness built on Vercel's eve framework, intended to eventually
replace the claude/codex/pi + orbal-net-CLI-glue setup we run today. The team immerses
in the current herdr / orbal-net / spawn.py workflow, daydreams, and writes a coherent
vision plus a concrete architecture. The defining bet: orbal-net is a *native eve
channel* (a pushed room message is an inbound turn), and eve's durable-backend nature
lets agents run remotely, closing the current "herdr can't wake a remote pane" gap.
Success = an RFC a lead could later turn straight into a build mission, with a clear
thesis, a primitive-mapping, a native-channel design, a remote-agent design, a
migration path, and a recommended first increment.

## In scope
The RFC must take a concrete position on each of these, not just survey options:
- Map eve's primitives onto our orchestration model: `instructions.md`, `tools/*`,
  `skills/*`, `subagents/*`, `channels/*`, `connections/*`, `sandbox/*`, durable
  sessions/turns (Vercel Workflows), and the AI SDK 7 terminal-UI package. What each
  buys us; where it is a clean fit vs a stretch.
- orbal-net as a native channel: design how the (post-push) SSE stream becomes a
  channel's inbound event source, so a pushed room message = a turn. Native emission of
  messages, progress events, and the 8 event kinds from the runtime - no `orbal-net`
  CLI shell-outs. Preserve consuming vs non-consuming semantics (read advances the
  cursor; peek/events do not) and the 3-layer room-membership rules.
- Deploy-as-backend / remote agents: how an eve agent on Vercel Functions/Workflows
  subscribes to a mission's orbal-net SSE stream and takes turns remotely; how this
  closes the remote-wake gap (the SSE push IS the wake, no herdr pane needed); the
  local-terminal (AI SDK TUI) vs remote-backend duality of one codebase.
- Map the 3-layer orchestrator / lead / worker + room-membership model onto eve
  (subagents vs separately-deployed agents; how `mission-<feature>` and `squad-<lead>`
  rooms map to channels/sessions; where membership enforcement lives).
- herdr's role in the new world: still the placement/process layer for *local* agents,
  or superseded for remote ones? What spawn.py has to change.
- Migration / replacement path from claude/codex/pi + CLI-glue to the eve harness:
  incremental coexistence, running one eve agent inside a fleet of legacy harnesses
  first, what spawn.py / AGENTS.md / the bootstrap change, and in what order.
- A ranked list of open questions/unknowns and a recommended first build increment.

## Non-goals
- No shipped code, no prototype, no spike. Design and prose only.
- Not building the harness or modifying spawn.py / AGENTS.md / orbal-net in this mission.
- Does not re-open or change the orbal-net-push design; it consumes push as a given.
- Not an eve-vs-other-frameworks bakeoff - eve is chosen. Light comparison only where it
  informs a risk.
- Not a Vercel deployment / billing / ops runbook.
- No entity or memory-fact writing; the RFC is a work artifact, not curated memory.

## Constraints
- Sequenced AFTER mission-orbal-net-push lands. The RFC's baseline is the post-push SSE
  model: agents subscribe to an SSE stream (`orbal-net stream`/`recv`, exact name is a
  push-mission decision), messages + events are pushed on arrival, `wait` and the poll
  loop are gone. Write against that model, NOT today's poll/`wait` path.
- eve is a Vercel beta (framework, APIs, and behavior may change before GA). Ground
  every eve claim in current docs (vercel.com/docs/eve and AI SDK 7 docs) and flag beta
  risk explicitly; design to concepts, not exact signatures.
- Preserve orbal-net coordination semantics unchanged: room model, 3-layer membership,
  read-advances-cursor vs peek/events-non-consuming, wire message shape, the 8
  progress-event kinds (task-start/done/error/abort, step, phase, blocked, handoff).
- No em dashes anywhere; use "-". Stay internally consistent with today's terms
  (herdr panes/tabs, mission-<feature>/squad-<lead>, spawn.py up/down/poke/bridge-pr).
- Deliverable is one markdown RFC committed to the `.botfiles` repo. Because it ships to
  a GitHub repo, the orchestrator bridges every live GitHub step (push + PR via
  `spawn.py bridge-pr eve-harness`); agents *prepare* the file/text, they have no
  `gh`/network and their clone origin is a local mirror.

## Acceptance criteria
- One self-contained RFC markdown (`orchestration/eve-harness.rfc.md`) readable cold by
  someone who knows neither eve nor our stack.
- Every In-scope question answered with a concrete position, not a menu.
- Contains, concretely: an eve-primitive -> our-model mapping table; a native-channel
  design (SSE frame -> eve turn) with a sequence sketch; a remote-agent design that
  names exactly how the remote-wake gap closes; a migration path with an ordered first
  few steps; a ranked open-questions list; a recommended first build increment.
- Every eve claim is grounded in a cited current doc; beta-churn risks are called out.
- No factual conflict with the post-push orbal-net model (no reference to `wait`/polling
  as the live mechanism).
- No em dashes; consistent vocabulary with the existing workflow.

## Affected areas
- New file only: `orchestration/eve-harness.rfc.md`.
- Read (do NOT modify) for grounding: `orchestration/spawn.py`, `AGENTS.md`,
  `.botfile/memory/tools/orchestration.md`, `orchestration/orbal-net-push.brief.md`,
  and the eve / AI SDK 7 docs.

## Risks and unknowns
- Dependency risk: orbal-net-push may land differently than its brief (SSE frame format,
  the `stream`/`recv` command name, cursor-advance vs explicit-ack on the stream). The
  RFC should cite the push brief and mark where its design hinges on a push specific.
- eve beta churn: channels / subagents / durability APIs may shift before GA; anchor the
  design in concepts.
- Channel-fit unknown: whether an eve channel cleanly supports a long-lived SSE inbound
  subscription with per-room turn creation, or whether it needs a custom channel.
  Investigate the channel contract before asserting the clean-fit claim.
- Remote-wake reality: can a durable eve session actually stay live (and cheap) enough to
  hold an SSE subscription, or does it need a webhook-style re-entry per message? The
  cost/latency of Fluid Compute for an always-listening agent is a real unknown.
- 3-layer mapping tension: eve subagents share the parent's deployment/identity, while
  our leads/workers are separate identities; and room-membership enforcement lives in
  orbal-net today, not in the harness. Name where each responsibility should live.
- Consuming-semantics preservation: an eve channel that auto-turns on every pushed
  message must not silently clobber the read-vs-peek cursor contract.

## Team plan
- repo: `/Users/percules/.botfiles`
- **rfc-lead** (claude/opus): owns the RFC end to end - immerses, daydreams, sets the
  thesis (eve-native channel + remote-backend, as the eventual replacement), fixes the
  document outline and the primitive-mapping shape before workers diverge, integrates
  both workers' research into one coherent document, writes the migration path and the
  recommended first increment, and relays the human-only GitHub bridge steps.
  - **worker-eve** (claude/sonnet): grounds the eve / AI SDK reality - the primitives
    (channels, subagents, sandbox, durable sessions/turns, AI SDK 7 TUI), the channel
    contract, the deploy / Fluid-Compute model, and beta caveats, all cited from current
    docs. Produces the eve-primitive -> our-model capability mapping and the
    remote/deploy feasibility read.
  - **worker-integration** (claude/sonnet): designs the orbal-net-native-channel
    (post-push SSE -> turn) and the 3-layer / room-membership mapping against today's
    spawn.py / orbal-net / herdr workflow. Produces the migration path from CLI-glue to
    native, and the ranked open-questions/risks list.
