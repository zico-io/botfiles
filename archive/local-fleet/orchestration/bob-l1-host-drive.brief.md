# Mission brief: bob-l1-host-drive

Long name: "close the four gaps the bob-l1 host-drive shakedown found so bob-as-L1 can do a real end-to-end run on the host: adopt the AI SDK 7 terminal UI / eve-client as bob's durable front end WITH approval rendering (so approval-gated spawn_bridge_pr/spawn_down are answerable and approve->execute actually runs), advertise the shared orbal-net server on the LAN egress IP so SANDBOX/VM agents can reach it, fix spawn_up's roster-path resolution, and land a green real-fleet run driven by a human at bob's TUI with a real approval-gated GitHub write"

## Goal
The bob-l1-host-wiring mission proved bob-as-L1 LAUNCHES and DRIVES live on the host (shared
server, durable session, multi-room notify_human relay, per-room teardown, cross-platform
process control - all green with host-side leads). Taking it fully live - bob spawning a REAL
fleet and doing a REAL approval-gated GitHub write - then surfaced four concrete gaps. This
mission closes them so a human at bob's TUI can run a mission end to end: scope -> spawn a real
fleet on the shared server -> drive it -> approve a real spawn_bridge_pr (real PR) and
spawn_down (real teardown). Success = that green run, on the real host, with the approval
prompts rendered and answerable in bob's front end.

The four gaps (from the shakedown):
- #5 (the big one): bob's approval-gated tools PARK correctly (proven) but bob's thin front
  end (`bob.ts` channel + `client/bob-tui.ts`) cannot ANSWER an approval - only the generic
  eve channel / eve-client speaks the `inputResponses` protocol. DECIDED: adopt the AI SDK 7
  terminal UI / eve-client as bob's durable front end, with full approval rendering, so
  approve->execute runs.
- #4: `bin/bob` binds/advertises the shared server at `127.0.0.1:4100` (loopback), but
  SANDBOX/VM agents need the LAN egress IP (spawn.py's per-mission path uses `_advertise_host()`
  / `ORBAL_NET_ADVERTISE_HOST`). Advertise the LAN IP for the shared server so a real SANDBOX
  fleet can reach coordination.
- #6: `spawn_up` resolves `rosterPath` relative to eve's cwd (the bob repo), not `.botfiles`,
  so relative roster paths fail. Resolve robustly (absolute, or relative to ORCHESTRATION_DIR's
  parent).
- #7: the `BOTFILE_NO_SANDBOX` local-spawn path does not get a local claude pane to ready (it
  does not pre-answer claude's first-run prompts the sandbox path handles). Secondary: with #4
  fixed the real run targets SANDBOX, so #7 is a nice-to-have (a working light local mode),
  not the critical path.

## In scope
Two repos. PRIMARY `/Users/percules/dev/bob` (mission clone); `spawn.py`/`AGENTS.md` live in
`.botfiles` - changes prepared as a diff for the orchestrator to apply (seeded reference).
Build on the bob-l1-host-wiring deliverable (already on main) and the merged microsandbox pin.

- #5 - AI SDK 7 TUI / eve-client front end with approvals (the core workstream):
  - Make bob's interactive front end the AI SDK 7 terminal UI over the generic eve channel
    (`agent/channels/eve.ts` is already present), REPLACING or superseding the thin
    `client/bob-tui.ts` for the L1 human loop. It MUST render assistant text, tool cards, and
    - critically - approval prompts (`input.requested`, display=confirmation, approve/deny),
    and let the human ANSWER them (post the `InputResponse {requestId, optionId}` so the turn
    un-parks and execute runs).
  - It MUST ride bob's ONE durable `bob:<host>` session (RFC S4): the conversation resumes on
    relaunch, exactly as the thin client does today. This is RFC open question #1 (the parent
    RFC and the spike both flagged that `@ai-sdk/tui`'s `runAgentTUI` is documented
    local/in-process/non-durable). Investigate the seam FIRST: if `runAgentTUI` can be driven
    over a durable eve session (or a `@ai-sdk/workflow` WorkflowAgent-backed session), use it;
    if not, build the render layer over eve's durable session stream (the RFC S4 fallback) but
    still reuse `@ai-sdk/tui`'s rendering + approval-prompt primitives. Either way the durable-
    resume property and the approval-answer path are the two hard requirements.
  - `notify_human` relays must surface in this TUI (they already land as `bob-from:
    mission-relay` turns in the durable session).
- #4 - shared server LAN reachability: `bin/bob` advertises the shared server on the LAN
  egress IP (reuse the `_advertise_host()` / `ORBAL_NET_ADVERTISE_HOST` mechanism spawn.py
  already has; `orbal-net serve` already binds all interfaces, so this is about the ADVERTISED
  `ORBAL_NET_URL`/`ORBAL_NET_SHARED_URL`, not the bind). Confirm a SANDBOX/VM agent reaches the
  shared server at that URL. If spawn.py's shared path needs to pass the LAN URL through
  (vs bob's loopback), prepare that as part of the `.botfiles` diff.
- #6 - `spawn_up` (and sibling tools that take a path) resolve `rosterPath` so a path relative
  to the orchestration dir works, not only an absolute one (or document + enforce absolute).
- #7 - secondary: EITHER make the `BOTFILE_NO_SANDBOX` local path pre-answer claude's first-run
  prompts so a light local claude lead reaches ready, OR explicitly scope the real run to
  SANDBOX and mark NO_SANDBOX local mode as unsupported-for-now. Do not let #7 block #4/#5.
- Update `docs/HOST-RUN-PLAYBOOK.md` + `HOST-SHAKEDOWN.md` for the TUI front end + the LAN
  advertise + the real green-run steps; provide the orchestrator a run sheet for the LIVE run.

## Non-goals
- The LIVE green run itself (bob spawning a real SANDBOX fleet + a real GitHub write under
  human-approved prompts) is executed by the ORCHESTRATOR + human on the host AFTER the code
  lands - it is inherently host + human-in-the-loop (the approval prompt is FOR a human). In
  VM, validate the TUI's durable-resume + approval-answer against a stub/gated tool, the LAN
  advertise, and spawn_up path resolution; deliver the run sheet for the live run.
- Do not change spawn.py's per-mission (legacy) path or the shared-path gating - only the LAN
  URL passthrough if strictly needed, additive.
- Do not regress the leaf role, the durable session, the connector's exactly-once/cursor/
  park-gate, the approval-gating policy (`approval: always()` on the two tools stays), the
  coding tools, or the shared-server model from bob-l1-host-wiring.
- Do not re-open the microsandbox pin (PR #3) or the shared-server decision.
- No remote/Vercel-deployed orchestrator. Local-first. No entity/memory writes.

## Constraints
- Ground on and reuse: the bob-orchestrator RFC (S4 interactive session + the AI SDK 7 TUI
  durability open question #1, S6 approval gating), the bob-l1-build + bob-l1-host-wiring
  deliverables (on main), and the shakedown findings (seeded at `docs/reference/`). Reuse
  `@ai-sdk/tui`'s rendering + approval primitives; reuse the proven durable-session client
  (`agent/lib/eve-session.ts`) where the render layer needs the durable stream.
- eve baseline: `eve@0.22.1`, Node >=24, microsandbox (`agent/sandbox.ts`) with the one-time
  `npx eve dev` libkrun install per host; AI Gateway via `vercel link`. `eve start` RESUMES;
  never wipe `.workflow-data` in bob's launch path.
- Approval protocol: the gate stays `approval: always()`; the front end answers via
  `InputResponse {requestId, optionId}` (approve/deny) posted back through the eve channel /
  eve-client - do not weaken or bypass the gate, only make it answerable.
- No em dashes; use "-". Consistent vocabulary (herdr, orbal-net serve/recv/peek/send/event,
  continuation token, session/turn, mission-<feature>/squad-<lead>, orchestrator seat,
  input.requested/inputResponses).
- Two-repo delivery: bob changes -> mission branch (orchestrator bridges the PR to
  `zico-io/bob`); any spawn.py/AGENTS.md change -> a diff for `.botfiles`. Agents have no
  gh/network; prepare artifacts, the orchestrator executes every live git/GitHub step.

## Acceptance criteria
- bob's front end renders and ANSWERS approval prompts: a gated tool call (e.g. `spawn_down`)
  shows an approve/deny prompt in the TUI, and answering "approve" un-parks the turn and runs
  execute; "deny" does not. Demonstrated in-VM against a real or stubbed gated tool.
- The front end rides the durable `bob:<host>` session: launch, converse, relaunch -> the same
  conversation resumes (RFC S4 bet 1, unregressed), and `notify_human` relays appear in it.
  If `runAgentTUI` cannot ride a durable session, the delivered render-over-durable-stream
  fallback does, and the limitation is documented.
- `bin/bob up` advertises the shared server on the LAN egress IP; a second host/VM process can
  reach `ORBAL_NET_URL`; the durable session + connector still work on that URL.
- `spawn_up` accepts a roster path relative to the orchestration dir (not only absolute).
- Updated `docs/HOST-RUN-PLAYBOOK.md` + a live run sheet for the green run; `HOST-SHAKEDOWN.md`
  records what is proven in-VM vs run live. No-regression proofs (`proof:leaf`/`durable`/
  `coexistence`/`shared-server`) still green (orchestrator re-runs the KVM/Vercel ones on host).
- No em dashes; no factual conflict with the RFC, prior deliverables, or the orbal-net model.

## Affected areas
- `/Users/percules/dev/bob`: a new/replaced TUI front end (AI SDK 7 TUI / eve-client over the
  eve channel + durable session, with approval rendering + inputResponses), `bin/bob` (LAN
  advertise + launch the new TUI), `agent/tools/spawn_up.ts` (path resolution), possibly
  `agent/channels/bob.ts`/`eve.ts` wiring, `client/` (the TUI), `proofs/` (a TUI-approval +
  durable-resume proof), docs.
- Prepared for `.botfiles` (orchestrator-applied): only if the shared LAN-URL passthrough needs
  spawn.py - additive.
- Seeded reference (orchestrator adds; remove before final): the RFC, the shakedown findings,
  current spawn.py/AGENTS.md, `HOST-SHAKEDOWN.md`.

## Risks and unknowns
- #5 durability of the AI SDK 7 TUI is RFC open question #1, still unresolved: `@ai-sdk/tui`'s
  `runAgentTUI` is documented local/in-process/non-durable. The mission may find it cannot ride
  a durable eve session and must build the render layer over the durable session stream (the
  RFC S4 fallback) - budget for that; the two hard requirements (durable resume + approval
  answer) must hold even if full `runAgentTUI` reuse does not.
- Approval answer wiring: confirm the exact eve endpoint/protocol for posting an InputResponse
  through the eve channel over loopback (auth: the eve channel uses vercelOidc/localDev/
  placeholder - localDev applies on localhost). Get this from current eve docs + the built
  routes, not by guessing.
- #4 LAN advertise must not break the loopback host-side path (bob's own connector + eve reach
  the server); advertise LAN in ORBAL_NET_URL while keeping local reachability.
- The LIVE green run needs a real SANDBOX fleet (VM boot + real claude + AI Gateway) and a real
  GitHub write under human approval - inherently host + human, run by the orchestrator; the
  build fleet cannot fully self-certify it (in-VM has no KVM/Vercel), same boundary as before.
- Two workers touching bin/bob + the front end can collide: the lead fixes bin/bob's launch
  shape first; worker-tui owns the TUI/front-end + approval path, worker-plumbing owns
  bin/bob LAN advertise + spawn_up path + #7 - coordinate the bin/bob edits through the lead.

## Team plan
- repo: `/Users/percules/dev/bob`
- **drive-lead** (claude/opus): owns the mission - integrates the TUI front end with the
  plumbing fixes, fixes bin/bob's launch shape before workers diverge, owns the in-VM
  validation (durable-resume + approval-answer + LAN-advertise + path resolution), the updated
  host playbook + `HOST-SHAKEDOWN.md` + the live green-run run sheet, the spawn.py diff (if any)
  for `.botfiles`, and the PR-body text. Relays the two-repo bridge asks.
  - **worker-tui** (claude/sonnet): the AI SDK 7 terminal UI / eve-client front end (#5) - ride
    the durable `bob:<host>` session (investigate the runAgentTUI-over-durable-session seam
    first; fall back to render-over-durable-stream reusing @ai-sdk/tui primitives), render
    assistant text / tool cards / notify_human relays, and RENDER + ANSWER approval prompts
    (input.requested -> InputResponse approve/deny so approve->execute runs). Delivers a
    TUI-approval + durable-resume proof.
  - **worker-plumbing** (claude/sonnet): #4 (bin/bob advertises the shared server on the LAN
    egress IP via _advertise_host/ORBAL_NET_ADVERTISE_HOST, keeping loopback host-side
    reachability; confirm a VM/second process reaches it), #6 (spawn_up roster-path resolution
    relative to the orchestration dir), and #7 (either pre-answer local claude's first-run
    prompts for a working NO_SANDBOX light mode, or scope the real run to SANDBOX and mark local
    mode unsupported). Refreshes the launch/teardown docs it touches.
