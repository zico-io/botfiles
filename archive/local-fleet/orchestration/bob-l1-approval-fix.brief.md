# Mission brief: bob-l1-approval-fix

Long name: "unblock bob's host green run by replacing eve's broken runtime approval gate (approval: always()) on the two hard-to-reverse tools with a conversational-confirmation gate that works on eve's normal turn loop, and replace the false-green fake-backend approval proof with a real-eve one; eve's own approval-gated-tool resume is a confirmed upstream beta bug (vercel/eve #533/#460) filed and out of our hands"

## Goal
The host green run is blocked by a confirmed eve BETA bug: an `approval: always()` tool,
on approve, has eve re-invoke the model with the tool's `tool_use` block but NO matching
`tool_result` -> Anthropic 400 (dangling tool_use) -> the approved tool never runs and the
session dies. Root-caused and reproduced directly over HTTP on a trivial tool (no bob
channel/TUI involved), confirmed present in eve@0.22.1 AND the latest 0.22.4, and it lives
in eve's `[harness.tool-loop]`, not bob's code. Filed upstream (vercel/eve #533, with our
minimal repro + the "still broken in 0.22.4" signal; duplicates #460, p1). It is NOT
fixable in bob and not fixed by a version bump.

This mission makes bob's human-in-the-loop gate on the two hard-to-reverse tools
(`spawn_bridge_pr`, `spawn_down`) work TODAY by moving the gate OFF eve's broken runtime
approval and ONTO a conversational-confirmation flow that rides eve's ordinary turn loop
(no tool_use parking, no approval-resume). Success = the finale runs: bob asks for
confirmation in a normal turn, the human approves, and only then does the irreversible
action execute - proven by a REAL-eve (KVM + AI Gateway) acceptance proof, not a fake
backend. When eve fixes #533 we can switch back to `approval: always()`; that path stays
documented.

## In scope
Repo: `/Users/percules/dev/bob` (bob-only; NO spawn.py/.botfiles change). Build on the
bob-l1-host-drive deliverable (on main) and the merged microsandbox pin.

- Conversational-confirmation gate for `spawn_bridge_pr` + `spawn_down` (RFC S6 human-in-the-
  loop, preserved - only the MECHANISM changes):
  - Remove `approval: always()` (eve/tools/approval) from both tools. They become ordinary
    (ungated) tools so a model call no longer parks at `input.requested` (which is what
    triggers the broken resume).
  - Add a gate that is enforced BEYOND pure prompt-honoring (a bare "the instructions tell
    bob to ask first" is too soft for a live GitHub write). The required shape: a TOOL-SIDE
    two-phase confirmation - the FIRST call performs NO side effect; it returns a
    confirmation challenge (a short nonce/token the tool issues, tied to the exact action +
    args) and asks the human to confirm; the action executes ONLY on a SECOND call carrying
    that exact issued token, which the tool verifies was issued this session for this action.
    So the model cannot fire the side effect in one shot, and the human must actively supply
    the confirmation - a real gate on normal turns. (An equivalent robust design is fine;
    the hard requirement is: no single model call can trigger the irreversible action, and a
    human turn is structurally required in between.)
  - Update bob's `agent/instructions.md` Human-turns section: describe the ask-confirm flow
    (call the tool, relay its confirmation challenge to the human, wait for the human's
    reply, call again with the token) replacing the old "expect an approval prompt" wording.
  - Remove or clearly mark-dormant the now-unused runtime-approval machinery (the
    `inputResponses` answer path in `bob.ts` / `sendInputResponse` in `eve-session.ts` /
    `proof_approval_gate` / the approval rendering+answer in `client/bob-tui.ts`) - keep the
    diff minimal; if kept for the future eve-fix path, gate it clearly with a comment linking
    vercel/eve #533 and a one-line "revert to approval: always() when #533 lands" note.
- Real-eve acceptance proof (replaces the false green): a proof that stands up a REAL
  `eve start` (microsandbox + AI Gateway) and drives the conversational gate end to end
  through `client/bob-tui.ts` (or the /bob/message HTTP path): (a) confirm -> the action's
  execute runs; (b) no-confirm / wrong-token / deny -> the action does NOT run; (c) the flow
  never produces a dangling-tool_use / MODEL_CALL_FAILED (it uses no runtime approval). This
  proof needs KVM + a Vercel token, so it is HOST-BOUND - authored here, run by the
  orchestrator on the host (like the other eve-turn proofs).
- Retire the false-green mechanism: demote `proofs/approval-wire.ts` (fake-bob-eve backend,
  no real model) from an acceptance proof to at most a unit-level check, and REMOVE reliance
  on `proof_approval_gate` for acceptance. Keep the minimal upstream HTTP repro (the ~30-line
  one that reproduces #533) committed as `proofs/eve-approval-bug-repro.ts` with a header
  linking #533, as a documented regression marker: when it starts PASSING (eve fixed it), we
  can switch back to the native gate.
- Docs: update `docs/HOST-RUN-PLAYBOOK.md` + `HOST-SHAKEDOWN.md` for the conversational gate
  + the finale run sheet (bob spawns a real SANDBOX fleet -> the human confirms a real
  `spawn_bridge_pr` + `spawn_down` via the conversational flow), and record the eve #533
  root-cause + the revert-when-fixed plan.

## Non-goals
- Do NOT try to fix eve itself or patch its tool-loop internals - the bug is upstream
  (vercel/eve #533), filed, and out of scope. Do not bump the eve pin as the fix (0.22.4 has
  the same bug).
- The LIVE finale run (bob spawning a real SANDBOX fleet + the human confirming a real
  GitHub write) is executed by the ORCHESTRATOR + human on the host AFTER this lands - the
  confirmation is FOR a human. In-VM: validate the gate logic (two-phase, token enforcement)
  with unit tests + author the host-bound real-eve proof.
- Do not weaken the human-in-the-loop guarantee: the point is a REAL gate on the two
  irreversible tools, just on a working mechanism. A pure prompt-only "please ask first"
  with no tool-side enforcement is NOT acceptable.
- Do not regress the durable session, the connector/shared-server, the LAN advertise, the
  spawn_up path fix, the leaf role, or the coding tools. Do not change spawn.py/.botfiles.
- No remote/Vercel-deployed orchestrator. No entity/memory writes.

## Constraints
- Ground on: the host-drive shakedown finding (this brief), the bob-orchestrator RFC S6
  (human-in-the-loop rationale for the two tools), and the merged bob deliverables. The
  approval gate's INTENT (a live GitHub write / a teardown must not fire without a human)
  is unchanged; only the mechanism moves off eve's broken runtime approval.
- eve baseline: `eve@0.22.1` (pinned; do not bump), Node >=24, microsandbox (one-time
  `npx eve dev` libkrun install per host), AI Gateway via `vercel link`. `eve start` RESUMES;
  never wipe `.workflow-data`.
- The gate must ride eve's NORMAL turn loop - ordinary tool calls + ordinary assistant/human
  turns - with NO `approval:`-parked `input.requested`, since that is exactly what triggers
  #533. Confirm the finished flow produces zero MODEL_CALL_FAILED against real eve.
- No em dashes; use "-". Consistent vocabulary. Ships to a GitHub repo (`zico-io/bob`): the
  orchestrator bridges the PR; agents prepare branch/commits + PR text (no gh/network).

## Acceptance criteria
- `spawn_bridge_pr` and `spawn_down` no longer declare `approval: always()`; a single model
  call cannot trigger either side effect - a human turn supplying the tool-issued
  confirmation token is structurally required (unit-tested: first call = no side effect +
  challenge; second call with a wrong/absent token = refused; second call with the exact
  issued token = executes).
- A real-eve (KVM + Gateway) proof passes on the host: confirm -> executes; deny/no-token ->
  does not; and the run shows NO dangling-tool_use / MODEL_CALL_FAILED (verifiable in the
  eve log). Authored here; the orchestrator runs it on the host.
- `agent/instructions.md` Human-turns section describes the ask-confirm flow; the old
  runtime-approval wording is gone; the now-unused approval-answer code is removed or
  clearly dormant with a `vercel/eve #533` + revert-when-fixed comment.
- `proofs/approval-wire.ts` is demoted (not an acceptance gate); `proof_approval_gate` no
  longer backs acceptance; `proofs/eve-approval-bug-repro.ts` is committed as a documented
  #533 regression marker.
- Docs updated (HOST-RUN-PLAYBOOK + HOST-SHAKEDOWN) for the conversational gate + the finale
  run sheet + the eve #533 root-cause/revert plan. No regression in the existing green proofs
  (`proof:leaf`/`durable`/`coexistence`/`shared-server`). No em dashes.
- A PR body prepared for the orchestrator to bridge to `zico-io/bob`.

## Affected areas
- `/Users/percules/dev/bob`: `agent/tools/spawn_bridge_pr.ts` + `agent/tools/spawn_down.ts`
  (drop approval, add the two-phase confirmation guard + a shared confirm-token helper, e.g.
  `agent/lib/confirm-gate.ts`), `agent/instructions.md` (ask-confirm flow), `bob.ts` /
  `agent/lib/eve-session.ts` / `client/bob-tui.ts` (remove/dormant the runtime-approval
  answer path), `agent/tools/proof_approval_gate.ts` (retire from acceptance),
  `proofs/` (new real-eve gate proof; demote approval-wire; add eve-approval-bug-repro),
  `docs/HOST-RUN-PLAYBOOK.md`, `HOST-SHAKEDOWN.md`, `docs/PR-BODY-*.md`.
- New PR to `zico-io/bob` (orchestrator-bridged). No `.botfiles` change.
- Seeded reference (orchestrator adds; remove before final): this brief / the root-cause
  writeup, the RFC (S6).

## Risks and unknowns
- The gate must be genuinely robust, not theater: a two-phase tool-side token is the
  requirement, but get the token lifecycle right (issued per (action, args, session), single-
  use, not guessable, not reusable across a different action) so the model cannot self-serve
  the confirmation. Unit-test the abuse cases (reuse, wrong action, stale token).
- Human-UX through bob's thin TUI: the confirmation challenge + the human's reply are two
  normal turns; make sure the TUI renders the challenge clearly and the human's plain reply
  (the token, or "confirm <token>") routes back as an ordinary message (not the now-removed
  approval path). Keep the durable-resume property intact.
- Retiring the approval-answer code must not break the durable-session send path (bob.ts's
  message route is load-bearing for normal turns) - remove ONLY the inputResponses branch,
  keep the message path.
- Real-eve proof is host-bound (no KVM/Gateway in the build VM); author it to run on the
  host and validate the gate LOGIC in-VM with unit tests. Do not claim the real-eve green
  in-VM.
- When eve fixes #533, the native `approval: always()` path is preferable (less bespoke);
  keep the switch-back cheap and documented so this is not a permanent fork.

## Team plan
- repo: `/Users/percules/dev/bob`
- **fix-lead** (claude/opus): owns the gate design (the two-phase confirm-token contract +
  where enforcement lives), integration, the instructions rewrite, the docs (playbook +
  shakedown + the #533 root-cause/revert plan), the in-VM unit validation + the host run
  sheet, and the PR-body text. Fixes the shared confirm-gate shape before workers diverge.
  - **worker-gate** (claude/sonnet): implement the two-phase confirmation on
    `spawn_bridge_pr` + `spawn_down` (drop `approval: always()`, add the shared
    `confirm-gate` helper with a per-(action,args,session) single-use token), update
    `agent/instructions.md` Human-turns for the ask-confirm flow, and remove/dormant the
    now-unused runtime-approval answer path (bob.ts inputResponses branch, sendInputResponse,
    client TUI approval rendering) with a `vercel/eve #533` + revert-when-fixed comment.
    Unit-tests the token abuse cases.
  - **worker-proof** (claude/sonnet): author the HOST-BOUND real-eve acceptance proof
    (`eve start` + AI Gateway, drive the gate end to end: confirm-executes / no-token-refused
    / no MODEL_CALL_FAILED); demote `proofs/approval-wire.ts` + retire `proof_approval_gate`
    from acceptance; commit the minimal `proofs/eve-approval-bug-repro.ts` (#533 regression
    marker) with a header linking the upstream issue. Confirms the existing green proofs
    still pass.
