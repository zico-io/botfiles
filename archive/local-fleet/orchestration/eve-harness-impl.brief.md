# Mission brief: eve-harness-impl

Long name: "eve-harness implementation based on our rfc"

## Goal
Build the RFC's recommended first increment (orchestration/eve-harness.rfc.md, section
10): a throwaway, single-agent proof-of-concept that falsifies-or-confirms the RFC's
core thesis before any spawn.py or fleet work is spent. The thesis: orbal-net can be a
native eve channel - a message pushed over orbal-net's SSE stream (`recv`) becomes an eve
turn, via a small standalone connector - and eve's durable Workflow-backed sessions let
that survive a redeploy. Success is not "a shipped harness"; success is a runnable PoC
plus a written, evidence-backed go/no-go verdict on the thesis. Three things must all
hold, or the RFC's direction is wrong and we learned it for the price of one throwaway
project:
1. A pushed room frame reliably mints an eve turn through the connector (SSE-frame -> turn).
2. A mid-conversation redeploy of the eve app resumes the session from its
   `<room>:<agent>` continuation token with no lost or duplicated frames (durability).
3. A deliberate restart of the connector process mid-conversation resumes from
   `--since <msgSeq>:<evtSeq>` with no lost or duplicated frames (connector-restart resume).

## In scope
The PoC product, built in a NEW standalone repo (see Affected areas):
- A minimal eve project (`agent/instructions.md`, `agent/agent.ts` with a model via AI
  Gateway, a single throwaway agent) that runs locally (`eve dev`) and deploys
  (`vercel deploy`).
- `agent/channels/orbal-net.ts` - a webhook-style custom channel (`defineChannel`): a
  short `POST /orbal-net/message` route that takes one already-arrived frame
  `{room, agent, text, msgSeq, evtSeq}` and calls `send(text, { continuationToken:
  "<room>:<agent>" })` to mint/resume the turn. The channel does NOT hold the SSE open
  (a Function cannot; see Constraints).
- The standalone **connector** process (Node/TS): holds one `orbal-net recv <room>
  --follow` subscription, POSTs each pushed frame to the channel webhook, persists its
  per-(room,agent) `msgSeq:evtSeq` cursor, and resumes with `--since` on restart. It is
  the sole cursor owner. Crash-restart safe from day one.
- Native outbound tools (`agent/tools/orbal_net_send.ts`, `_event.ts`, `_progress.ts`):
  thin POSTs straight to the mission's orbal-net server, so the agent emits messages and
  the 8 event kinds (task-start/done/error/abort, step, phase, blocked, handoff) as
  runtime tool calls, not CLI shell-outs.
- A repeatable test harness / script that exercises the three proofs above and records
  pass/fail evidence (frame in -> turn out; redeploy mid-convo -> resume; connector
  restart -> resume), plus a README documenting how to run it.
- The written go/no-go verdict: does the thesis survive contact, with the evidence.

## Non-goals
- No spawn.py deploy-path integration, no `deploy_eve_role()`, no fleet/multi-agent
  wiring, no herdr changes. The RFC is explicit: spawn.py follows proof, it does not lead.
- Not converting a real lead/worker role (that is RFC S9 step 3, a later mission).
- Not the production connector (multi-room, multi-agent multiplexing, supervision). One
  room, one agent, one connector is enough to prove the mechanic.
- Not resolving the sandbox/git-write-back gap (RFC S10 risk 1) - out of scope until a
  real worker role is converted.
- No changes to orbal-net itself (the Rust binary) or its protocol. It is consumed as-is.
- Not a Vercel ops/cost runbook; note limits observed, do not productionize.

## Constraints
- eve is a Vercel public beta (framework/APIs/behavior may change before GA). Pin the
  exact eve version used for this PoC and record it; design to concepts, not signatures.
- The eve channel/session is Vercel Function-backed with a hard `maxDuration` ceiling, so
  it CANNOT hold the long-lived SSE connection - that is precisely why the connector
  exists (RFC S5/S6.3). Do not try to make the channel listen; keep it webhook-shaped.
- Preserve orbal-net semantics exactly: `recv --follow` and `events`/`peek` are
  non-consuming; the connector is the one component that owns/advances the cursor.
- TypeScript/Node (eve + AI SDK 7). Keep dependencies minimal.
- No em dashes anywhere; use "-".
- PRECONDITIONS (orchestrator host-prep on `.botfiles`, done BEFORE the fleet spawns -
  NOT agent work in the mission clone):
  - Rebuild the sandbox image so its baked `orbal-net` has `recv`/SSE (push has merged),
    and so it carries the `eve` + `vercel` CLIs (Node 22 is already baked).
  - Extend `mission_secrets()` + entrypoint to proxy the host's Vercel credentials into
    the guest (read-only, same pattern as the claude/codex OAuth proxy), so an in-VM
    agent can `vercel deploy`. The human runs `vercel login` on the host once; the
    sandbox copies that credential in.
  - Create and `git init` the new standalone repo at the target path so `spawn.py up`
    can clone it.
  Agents may PREPARE the `.botfiles` diffs (mission_secrets, Containerfile) as text for
  the orchestrator to apply, but cannot edit `.botfiles` from the eve-harness clone.
- Ships to a NEW GitHub repo (created via the orchestrator). Spawned agents have no
  `gh`/network-to-GitHub and their clone origin is a local mirror, so the orchestrator
  bridges every live GitHub step (repo create, push + PR via `spawn.py bridge-pr
  eve-harness-impl`, settings). Agents prepare files/text; the orchestrator executes.
  Note: the sandbox HAS open NAT egress, so in-VM `npm`, AI Gateway model calls, and
  `vercel deploy` work - the GitHub bridge is only about `gh`/origin-push, not egress.

## Acceptance criteria
- The eve project runs under `eve dev` and deploys via `vercel deploy` (pinned eve
  version recorded).
- Proof 1 (SSE-frame -> turn): a message sent into an orbal-net room, over a real
  `recv`/SSE server, produces an eve turn through the connector+webhook, and the turn's
  `orbal_net_send`/`orbal_net_event` tool calls land back in the room - matching the
  RFC S5 sequence sketch. Recorded evidence.
- Proof 2 (durability): redeploy the eve app mid-conversation; the session resumes from
  its `<room>:<agent>` continuation token with zero lost and zero duplicated frames.
  Recorded evidence.
- Proof 3 (connector-restart resume): kill and restart the connector mid-conversation;
  it resumes from `--since` with zero lost and zero duplicated frames. Recorded evidence.
- The 8 event kinds emit as native tool calls (no `orbal-net` CLI shell-out from the
  agent).
- A README explains how to reproduce all three proofs from scratch.
- A written go/no-go verdict on the thesis, citing the evidence; if any proof fails, the
  verdict says so plainly and names what it implies for the RFC direction.

## Affected areas
- NEW standalone repo (the deliverable), default path `/Users/percules/dev/eve-harness`
  (orchestrator git-inits before `up`; final GitHub repo bridged by orchestrator):
  `agent/` (instructions.md, agent.ts, channels/orbal-net.ts, tools/orbal_net_*.ts),
  the connector process, the test harness, README.
- `.botfiles` (PRECONDITION host-prep only, orchestrator-applied): `sandbox/Containerfile`
  (eve+vercel CLI, orbal-net recv), `orchestration/spawn.py` `mission_secrets()` +
  `sandbox/entrypoint.sh` (Vercel cred proxy).
- Reference (read, do not modify): `orchestration/eve-harness.rfc.md` (the design of
  record - sections 5, 6, 9, 10 especially), `.botfile/memory/tools/orchestration.md`,
  `.botfile/memory/tools/sandbox.md`.

## Risks and unknowns
- Vercel-cred-proxy + in-VM deploy is the gating unknown: does copying the host's Vercel
  login into the guest actually let an in-VM agent `vercel deploy`? If not, the durability
  proof cannot run sandboxed and we fall back to a host-side deploy step. Validate this
  precondition before the fleet spends time on the product.
- orbal-net `recv`/SSE must genuinely be in the rebuilt image; the currently-installed
  binary only has `wait`. Confirm the image carries `recv` before Proof 1.
- eve channel contract for a webhook that mints a turn per pushed frame with an
  externally-supplied `continuationToken` - confirm `defineChannel`/`send` supports this
  shape in the pinned beta; it is the crux of Proof 1 (RFC S5, S10 risk 4).
- Ordering under concurrent frames: if two messages land for the same
  `continuationToken` while a turn is running, does eve queue or race the second `send()`?
  (RFC S10 risk 4.) The test harness should probe this.
- Cursor/`--since` boundary correctness: the notify/backfill race at reconnect is the
  sharp edge for Proofs 2 and 3 - exact resume, no gap, no dup.
- Beta churn in eve / AI SDK 7 mid-mission; pin versions and record them.

## Team plan
- repo: `/Users/percules/dev/eve-harness` (new; orchestrator creates before spawn)
- **poc-lead** (claude/opus): owns the PoC end to end. Scaffolds the standalone eve
  project, writes `agent/instructions.md` + `agent/agent.ts` + the webhook-style
  `agent/channels/orbal-net.ts`, fixes the SSE-frame -> turn contract and the
  `<room>:<agent>` continuation-token mapping before workers diverge, owns Proof 1
  (SSE-frame -> turn) and the integrated test harness, writes the README and the final
  go/no-go verdict, and prepares any `.botfiles` precondition diffs + the GitHub
  repo-create/PR requests as text for the orchestrator to bridge.
  - **worker-connector** (claude/sonnet): builds the standalone connector process (holds
    `orbal-net recv <room> --follow`, POSTs each frame to the channel webhook, persists
    and resumes the per-(room,agent) cursor with `--since`, crash-restart safe) and the
    native outbound tools (`orbal_net_send`/`_event`/`_progress`). Owns Proof 3
    (connector-restart resume).
  - **worker-eve-runtime** (claude/sonnet): stands the eve project up runnable and
    deployable (eve + vercel CLI, model via AI Gateway, `eve dev` locally and
    `vercel deploy`), wires session/turn creation to the continuation token, and owns
    Proof 2 (durability - redeploy mid-conversation, confirm resume with no lost/dup
    frames). Prepares the Containerfile/mission_secrets precondition diffs as text.
