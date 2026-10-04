# Mission brief: bob-l1-spike

Long name: "prove the two genuinely-new bets of the bob-orchestrator RFC's recommended first increment: (1) an all-day human front-end rides a durable eve session that rehydrates on relaunch, and (2) the notify_human multiplex - a mission-room frame produces a turn that posts into a concurrently-live human session with zero lost, duplicated, or raced turns"

## Goal
Execute the bob-orchestrator RFC's recommended first build increment (RFC S9 steps 1-3,
S10): build a THROWAWAY local bob L1 agent project and falsify or confirm the TWO claims
that are genuinely new relative to the already-proven leaf worker. Everything else in the
RFC is either already proven at the leaf (native channel, connector, exactly-once,
indistinguishability - bob-demo) or is straightforward local shell-wrapping / markdown
porting; this spike spends effort ONLY on the two new bets. Success = a clear GO/NO-GO
verdict, backed by a runnable proof for each bet, on whether the interactive-orchestrator
direction is sound enough to justify a real build. If either proof fails, we learn it
here, cheaply, before any fleet integration is spent on it.

The two bets to prove:
- Bet 1 (Proof A) - durable interactive session rehydrate: a human-facing terminal client
  attached to ONE durable eve session (addressed by a stable continuation token, e.g.
  `bob:<host-identity>`) resumes the SAME conversation after the `eve start` process is
  killed and restarted (and, separately, after a simulated redeploy / fresh build). The
  human "reopens bob" and the prior conversation is intact - resume, not restart. This is
  the RFC's #1 risk: `@ai-sdk/tui`'s `runAgentTUI` is documented local/in-process/non-
  durable, so the proof is that a client over eve's session-stream API rides durable state.
- Bet 2 (Proof B) - the notify_human multiplex: bob runs the human-facing session AND at
  least one mission-room session concurrently under one agent identity, on DIFFERENT
  continuation tokens (`bob:<host>` vs `orbal-net:<room>:bob`). An inbound orbal-net room
  frame mints a room-session turn that calls a `notify_human` tool, which posts into the
  concurrently-live human session. Prove zero lost, duplicated, or raced turns across the
  two sessions of the one agent when a room frame lands while the human session is (or is
  not) mid-turn.

## In scope
- Scaffold a throwaway bob L1 eve project at `/Users/percules/dev/bob-l1` by REUSING the
  proven leaf pieces (copied into the seed clone): `agent/channels/orbal-net.ts`, the
  `agent/tools/orbal_net_*.ts` tools, and `connector/`. Do NOT reinvent them. Add only the
  L1-new pieces the two proofs need: the durable human-facing session + terminal client
  (Proof A), the `notify_human` tool + concurrent room-session wiring (Proof B), and one
  minimal ported skill only if a proof needs it (otherwise skip - YAGNI).
- Proof A runner: open a durable human session via the terminal client, exchange a few
  turns (plant a codeword), kill and restart `eve start`, reattach on the same continuation
  token, and assert the codeword / full history survives (resume not restart). Repeat for a
  simulated redeploy / fresh build. Reuse the leaf PoC's resume choreography (let a turn
  checkpoint before kill; allow a beat to rehydrate) - it is documented, do not rediscover.
- Proof B runner: run the human session and one mission-room session concurrently; deliver
  an orbal-net room frame (via the reused connector, subscribed to a throwaway room on the
  mission's own orbal-net server) that produces a room turn calling `notify_human`; assert
  the human session receives exactly one relayed turn, in order, no dup/loss, including the
  race case (frame lands while the human session is mid-turn). Reuse the connector's park-
  gated per-(room,agent) serialization and cursor discipline from the leaf.
- A `VERDICT.md` in the spike repo: GO/NO-GO per bet, the proof commands + observed output,
  the load-bearing findings, and any refinement the proofs surface (mirrors the eve-harness-
  impl PoC's VERDICT.md).
- An evidence summary prepared as text for `.botfiles` (`orchestration/bob-l1-spike.evidence.md`),
  go/no-go with the key proof output, in the style of `orchestration/bob-demo.evidence.md`,
  for the orchestrator to commit + bridge.

## Non-goals
- NOT production code. This is a throwaway spike to falsify two claims; hardening,
  polish, and full feature coverage are out of scope. Build the minimum that proves each bet.
- Not proving anything already proven at the leaf: the native channel mechanic, the
  connector's exactly-once / cursor / resume, and indistinguishability are GIVENS (bob-demo,
  eve-harness-v0). Reuse, do not re-prove.
- Not the `spawn_*` / `herdr_*` orchestration tools, not the GitHub-bridge relocation, not
  the full `/scope-mission` + `/spawn-team` skill port, not the migration steps 4-7, not
  the multi-room (N>1) attach/detach connector surface. Those are later increments (RFC S9
  steps 4+); a single mission room is enough to prove Bet 2.
- No remote/Vercel-DEPLOYED orchestrator. Local-first: `eve start` on the mission host/VM,
  sharing the LAN with orbal-net, exactly like the leaf v0.
- Not pushing the throwaway spike code to GitHub. The spike + VERDICT.md stay LOCAL; only
  the evidence summary is bridged into `.botfiles`.
- No entity or memory-fact writing.

## Constraints
- Ground on the proven stack, reuse its code: the bob-orchestrator RFC
  (`orchestration/bob-orchestrator.rfc.md`, sections 4, 5, 9, 10 especially - seeded into
  the clone), the leaf-worker harness `/Users/percules/dev/bob` (its `agent/`, `connector/`,
  `CONTRACT.md` - the relevant pieces seeded into the spike clone), and the post-push
  orbal-net model (`recv`/SSE, no `wait`/poll).
- eve environment reality (from `orchestration/eve-harness-v0.handoff.md` sections 4-5,
  authoritative): pin `eve@0.22.1` + Node >=24 (both baked into the mission VM image).
  `eve start` (production server, port 3000) RESUMES durable sessions; `eve dev` (port 2000)
  does NOT - use `eve start` for the proofs, never conflate them. Wipe `.workflow-data` per
  local run (a real deploy gets a fresh store). eve model calls need Vercel AI Gateway: the
  VM has the host `vercel` cred proxied in; link non-interactively with
  `vercel link --yes --scope zico-io --project <name>` (writes `.env.local` with a fresh
  `VERCEL_OIDC_TOKEN`); `npx eve link` needs a TTY and will NOT work. Do not burn time
  rediscovering this - it is documented in the handoff.
- eve does NOT durably queue concurrent deliveries to one continuation token (proven at the
  leaf) - which is WHY Bet 2 uses two different tokens for the two sessions. Preserve that.
- No em dashes anywhere; use "-". Consistent vocabulary with the workflow (herdr, orbal-net
  recv/peek/send/event, continuation token, session/turn, mission-<feature>/squad-<lead>).
- Two deliverable surfaces, two repos: the spike (code + VERDICT.md) is committed to the
  mission clone of `/Users/percules/dev/bob-l1` and harvested LOCAL (not GitHub). The
  evidence summary is prepared as text; the orchestrator commits it to `.botfiles` and
  bridges the PR. Spawned agents have no `gh`/network and their clone origin is a local
  mirror - prepare artifacts as files/text, the orchestrator executes every live GitHub step.

## Acceptance criteria
- A throwaway bob L1 eve project at `/Users/percules/dev/bob-l1` that builds and runs
  locally on `eve start` (`eve@0.22.1`, Node >=24), reusing the proven leaf channel /
  tools / connector rather than reimplementing them.
- Proof A is runnable and reproducible: a single command opens a durable human session,
  plants a codeword, and after an `eve start` kill+restart (and a simulated fresh build)
  reattaches on the same continuation token and asserts the conversation resumed (codeword +
  history intact). Output shows PASS/FAIL unambiguously.
- Proof B is runnable and reproducible: a single command runs the human + one room session
  concurrently, delivers a room frame that triggers `notify_human` into the human session,
  and asserts exactly-once, in-order relay across the two sessions - including the mid-turn
  race case. Output shows PASS/FAIL unambiguously.
- `VERDICT.md` states GO/NO-GO per bet with the commands, observed output, and findings.
- `orchestration/bob-l1-spike.evidence.md` (prepared for the orchestrator to bridge) gives
  the go/no-go + key evidence in the bob-demo.evidence.md style.
- No factual conflict with the bob-orchestrator RFC, the leaf v0 contract, or the post-push
  orbal-net model. No em dashes.

## Affected areas
- New throwaway repo: `/Users/percules/dev/bob-l1` (seeded by the orchestrator with copies
  of the proven leaf `agent/` + `connector/` + `package.json` from `/Users/percules/dev/bob`,
  the bob-orchestrator RFC, and `CONTRACT.md`; agents build the L1 additions + proofs on top).
- New file in `.botfiles` (orchestrator-committed): `orchestration/bob-l1-spike.evidence.md`.
- Read for grounding (seeded into the clone): `bob-orchestrator.rfc.md` (S4/S5/S9/S10),
  the leaf `agent/`+`connector/`+`CONTRACT.md`, `orchestration/eve-harness-v0.handoff.md`
  (sections 2-5), `orchestration/bob-demo.evidence.md` (evidence style), plus current eve /
  AI SDK 7 docs.

## Risks and unknowns
- Proof A is the single sharpest unknown (RFC open question #1): no fetched doc demonstrates
  a terminal client cleanly riding a durable eve session end to end. The proof may reveal
  `@ai-sdk/tui`'s render primitives are NOT reusable outside `runAgentTUI({ agent })`; if so,
  the fallback is fronting a `@ai-sdk/workflow` `WorkflowAgent`-backed session with a minimal
  custom render layer. The proof must ISOLATE the durability claim (session resumes on the
  same token) even if the fancy TUI rendering is stubbed - do not let TUI-rendering yak-
  shaving block proving the durable-session claim, which is the actual bet.
- Proof B cross-session ordering (RFC open question #2): whether eve serializes or races two
  concurrent turns across two sessions of one agent is undocumented - that is exactly what
  this proof measures. Design the race case deliberately (frame arrives while the human
  session is mid-turn), not just the happy path.
- Environment friction: the Vercel-link / OIDC-token dance and the `eve start` vs `eve dev`
  durability distinction are the two most likely time-sinks; both are documented in the
  handoff - follow it, do not rediscover. A fresh `npm ci` + `eve build` in the VM is slow;
  budget for it.
- Two workers on one eve project can collide: the lead scaffolds the SHARED L1 base (agent,
  durable session, reused channel/tools/connector) and fixes the project shape BEFORE the
  two proof workers diverge; each worker owns an isolated proof runner file (e.g.
  `proofs/durable.ts`, `proofs/multiplex.ts`) and its own report, not shared source.
- Reachability: Bet 2's connector must reach the mission's orbal-net server on the LAN (the
  leaf proved a local eve agent can). Use a throwaway room on the mission's own orbal-net
  server for the frame injection; do not stand up a separate server.

## Team plan
- repo: `/Users/percules/dev/bob-l1`
- **spike-lead** (claude/opus): owns the throwaway L1 project end to end - scaffolds the
  shared base (copies/reuses the proven leaf `agent/channels/orbal-net.ts` + `orbal_net_*`
  tools + `connector/`, wires the durable human-facing session + the agent), gets `eve build`
  / `eve start` + the Vercel-link running in the VM, fixes the project shape before workers
  diverge, integrates both proofs, writes `VERDICT.md` (GO/NO-GO per bet) and the
  `bob-l1-spike.evidence.md` text for the orchestrator to bridge, and relays bridge asks.
  - **worker-durable** (claude/sonnet): owns Proof A - the durable interactive-session
    rehydrate. Builds the minimal terminal client over eve's session-stream API on a stable
    continuation token, plants a codeword, kills+restarts `eve start` (and simulates a fresh
    build), and asserts resume-not-restart. Isolates the durability claim from TUI-rendering
    polish. Delivers `proofs/durable.ts` (or equivalent) + a PASS/FAIL report.
  - **worker-multiplex** (claude/sonnet): owns Proof B - the `notify_human` multiplex.
    Wires the reused connector to a throwaway room on the mission orbal-net server + the
    `notify_human` tool posting into the concurrently-live human session; drives a room frame
    (including the mid-turn race case) and asserts exactly-once, in-order relay across the two
    sessions. Delivers `proofs/multiplex.ts` (or equivalent) + a PASS/FAIL report.
