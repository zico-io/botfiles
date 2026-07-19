# Mission brief: bob-orchestrator

Long name: "our new harness 'bob' should be the orchestration harness -- user will launch bob via cli, bob will then be the persistent agent the human user interacts with throughout the day, and bob will use orbal-net for missions"

## Goal
Produce a north-star architecture RFC (a written design doc, NO shipped code) for turning
`bob` - today an eve LEAF worker (RFC S9 step 3, proven in `bob-demo`) - into the L1
ORCHESTRATION harness: the persistent agent the human launches from the CLI and interacts
with throughout the day, which drives missions over orbal-net. This inverts bob's role
from the bottom of the 3-layer model (a leaf that receives tasks) to the top (the pane the
human sits in, that scopes missions and drives leads). The defining bets: (1) eve's AI SDK
7 terminal-UI package is bob's all-day interactive front-end, backed by one durable eve
session so the conversation survives restarts; (2) bob joins `mission-<feature>` rooms as a
NATIVE eve channel (the same proven mechanic the leaf worker uses) to drive leads, rather
than shelling out to the `orbal-net` CLI. Success = an RFC a lead could later turn straight
into a build mission, with a clear thesis, an interactive-session design, a native-channel
orchestration design, an eve-skills port of the orchestration commands, and an ordered
migration path from the claude L1 to bob.

## In scope
The RFC must take a concrete position on each of these, not just survey options:
- Interactive all-day session: design how eve's AI SDK 7 terminal-UI package + a durable
  eve session give bob a persistent, human-interactive orchestrator front-end. How a
  human "launches bob via CLI" and talks to it all day; how the durable session keeps the
  conversation alive across restarts (leaning on the same Vercel Workflows durability the
  PoC proved for the leaf); the local-terminal (AI SDK TUI) role of the codebase.
- L1-as-native-channel: design how bob, as the orchestrator, joins `mission-<feature>`
  rooms as a native eve channel (reusing the proven leaf mechanic: SSE frame -> turn,
  `orbal_net_*` outbound tools) to relay the brief to leads and coordinate, instead of
  `orbal-net` CLI shell-outs. Preserve the 3-layer room-membership rules (orchestrator in
  `mission-<feature>` only, never messages a worker directly), consuming vs non-consuming
  semantics, and the 8 progress-event kinds.
- Orchestration tools: how bob drives placement/process/lifecycle - the parts that are NOT
  coordination messages. spawn.py (`up`/`down`/`poke`/`bridge-pr`), herdr placement, and
  the human-only GitHub bridge - modeled as eve tools bob calls. Note that bob as L1 runs
  LOCAL on the host, so it HAS `gh`/network (unlike spawned leaf agents); state where the
  bridge responsibility now lives.
- Port the orchestration commands to eve skills: design `/scope-mission` and `/spawn-team`
  (today claude-code skills) as portable eve `skills/*` that bob loads, mapping the current
  interview/scope/roster/spawn behavior onto the eve skills primitive. Keep the slash-
  command UX.
- Map the 3-layer orchestrator/lead/worker model onto bob-at-L1: how `mission-<feature>`
  and `squad-<lead>` rooms map to eve channels/sessions when the orchestrator is eve; where
  membership enforcement lives; bob driving existing claude/codex/pi leads unchanged.
- Migration / replacement path: bob is the intended eventual REPLACEMENT for the claude L1
  orchestrator. Design incremental coexistence (bob launchable alongside claude first),
  then cutover; what spawn.py / AGENTS.md / the bootstrap / the skills change, and in what
  order.
- A ranked list of open questions/unknowns and a recommended first build increment.

## Non-goals
- No shipped code, no prototype, no spike. Design and prose only.
- Not building bob-orchestrator or modifying spawn.py / AGENTS.md / the bob repo in this
  mission.
- Remote/Vercel-DEPLOYED orchestrator is a non-goal: bob-orchestrator is designed LOCAL-
  first (host process with gh/network, sharing the LAN with orbal-net). Name deployed-
  remote as a future increment, do not design it.
- Does not re-open or change the orbal-net-push design, the leaf-worker v0, or the native-
  channel wire contract - it consumes all three as proven givens.
- Not an eve-vs-other-frameworks bakeoff - eve is chosen. Light comparison only where it
  informs a risk.
- Not a Vercel deployment / billing / ops runbook.
- No entity or memory-fact writing; the RFC is a work artifact, not curated memory.

## Constraints
- Builds directly on the proven stack: the `eve-harness` RFC (`orchestration/eve-harness.rfc.md`,
  the design of record), the leaf-worker v0 in `/Users/percules/dev/bob` (README + `docs/`
  + `CONTRACT.md`), and the post-push orbal-net model (`recv`/SSE, no `wait`/poll). Write
  against these; reuse the native-channel + connector reference implementations, do not
  reinvent them.
- eve is a Vercel beta. Ground every eve claim (especially the AI SDK 7 terminal-UI package
  and the skills primitive) in current docs (vercel.com/docs/eve and AI SDK 7 docs); design
  to concepts, not exact signatures; flag beta-churn risk.
- Preserve orbal-net coordination semantics unchanged: room model, 3-layer membership,
  read-advances-cursor vs peek/events-non-consuming, wire message shape, the 8 progress-
  event kinds (task-start/done/error/abort, step, phase, blocked, handoff). The orchestrator
  never messages a worker directly.
- No em dashes anywhere; use "-". Stay internally consistent with today's terms (herdr
  panes/tabs, mission-<feature>/squad-<lead>, spawn.py up/down/poke/bridge-pr, orbal-net
  recv/peek/send/event).
- Deliverable is one markdown RFC committed to the `.botfiles` repo
  (`orchestration/bob-orchestrator.rfc.md`). Because it ships to a GitHub repo, the
  orchestrator bridges every live GitHub step (push + PR via `spawn.py bridge-pr
  bob-orchestrator`); agents *prepare* the file/text, they have no `gh`/network and their
  clone origin is a local mirror.

## Acceptance criteria
- One self-contained RFC markdown (`orchestration/bob-orchestrator.rfc.md`) readable cold by
  someone who knows neither eve nor our stack.
- Every In-scope question answered with a concrete position, not a menu.
- Contains, concretely: an interactive-session design (AI SDK 7 TUI + durable session) with
  a "launch bob, talk to it all day" walkthrough; an L1-native-channel orchestration design
  with a sequence sketch (bob relays brief -> lead over a room turn); an orchestration-tools
  mapping (spawn.py / herdr / GitHub bridge as eve tools) that states where the bridge lives
  now that L1 is local; an eve-skills port of `/scope-mission` + `/spawn-team`; a 3-layer
  mapping with bob at L1; an ordered migration path (coexist -> cutover) with the first few
  concrete steps; a ranked open-questions list; a recommended first build increment.
- Every eve claim is grounded in a cited current doc; beta-churn risks called out.
- No factual conflict with the eve-harness RFC, the leaf-worker v0 contract, or the post-
  push orbal-net model (no reference to `wait`/polling as the live mechanism).
- No em dashes; consistent vocabulary with the existing workflow.

## Affected areas
- New file only: `orchestration/bob-orchestrator.rfc.md`.
- Read (do NOT modify) for grounding: `orchestration/eve-harness.rfc.md`, the bob leaf-
  worker repo at `/Users/percules/dev/bob` (`README.md`, `docs/`, `CONTRACT.md`,
  `agent/channels/orbal-net.ts`, `agent/tools/orbal_net_*.ts`, `connector/`),
  `orchestration/spawn.py`, `AGENTS.md`, `.botfile/memory/tools/orchestration.md`,
  `.claude/commands/scope-mission.md`, `.claude/commands/spawn-team.md`, and the eve /
  AI SDK 7 docs.

## Risks and unknowns
- Interactive-durability fit: eve's durability was proven for a headless leaf turn. Whether
  the AI SDK 7 terminal-UI package cleanly rides a long-lived durable session for an all-day
  human-interactive loop (mid-turn streaming, interrupts, session rehydrate on restart) is
  the central unknown. Investigate the TUI-package contract before asserting a clean fit.
- Skills-primitive fit: whether eve's `skills/*` primitive can express the interactive,
  multi-step interview behavior of `/scope-mission` (AskUserQuestion-style prompting, the
  plan-pane loop) or only simpler skills. Mark where the port is a stretch.
- L1-channel tension: the orchestrator both talks to a human (TUI turns) AND to leads (room
  turns) - two inbound sources into one agent. Design how bob multiplexes a human turn and
  an orbal-net room turn without breaking the durable-session/cursor contract.
- Membership/identity: bob at L1 must be a first-class orbal-net member of every active
  `mission-<feature>` room and only those rooms; how it joins/leaves as missions come and go,
  and never leaks into a `squad-<lead>` room.
- GitHub bridge relocation: today the bridge exists because spawned agents lack gh/network;
  a LOCAL bob HAS them. Does the bridge collapse into a direct bob tool, and does that change
  any safety assumption (bob now pushes/PRs directly)? State the position.
- eve beta churn: the AI SDK 7 TUI package and skills APIs may shift before GA; anchor the
  design in concepts.

## Team plan
- repo: `/Users/percules/.botfiles`
- **rfc-lead** (claude/opus): owns the RFC end to end - immerses in today's L1 orchestrator
  workflow and the bob leaf-worker v0, sets the thesis (eve AI SDK 7 TUI + durable session as
  the all-day orchestrator, native channel to drive leads, eventual replacement of claude
  L1), fixes the document outline before workers diverge, integrates both workers' research
  into one coherent document, writes the migration path and the recommended first increment,
  and relays the human-only GitHub bridge steps.
  - **worker-eve** (claude/sonnet): grounds the eve reality for an interactive orchestrator -
    the AI SDK 7 terminal-UI package, durable-session-as-all-day-interactive-loop (streaming,
    interrupts, rehydrate), the `skills/*` primitive, local `eve start` as the front-end, all
    cited from current docs. Produces the interactive-session design and the eve-skills
    feasibility read for porting `/scope-mission` + `/spawn-team`.
  - **worker-orchestration** (claude/sonnet): designs the L1-as-native-channel orchestration
    (bob drives leads over room turns, reusing the proven leaf mechanic), the orchestration-
    tools mapping (spawn.py / herdr / GitHub bridge as eve tools, bridge relocation now that
    L1 is local), the 3-layer mapping with bob at L1, and the ordered migration path from the
    claude L1 to bob. Produces the ranked open-questions/risks list.
