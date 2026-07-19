# Mission brief: bob-tui-ink

Long name: "migrate bob's terminal front end from the hand-rolled readline/stdout thin client to the `ink` package (React for CLIs), fixing the current rough edges (prompt interleaving, streaming deltas with no label, ad-hoc stdout writes) with a proper component-rendered TUI - functional-minimal for v1, preserving durable resume + scrollback + mission-update relays + the confirm-gate flow exactly. Build v1, no rich extras (markdown/tool-cards/status-bar) yet."

## Goal
Replace `client/bob-tui.ts` - today a `readline` loop plus raw `process.stdout.write` calls -
with an `ink`-based (React-for-the-terminal) client that renders bob's durable `bob:<host>`
session as a clean, component-managed TUI. This is the "rich TUI follow-up" the host-drive
VERDICT and the bob-cli RFC both flagged as a known rough edge. v1 is FUNCTIONAL-MINIMAL: fix
the actual UX problems (a stable input box that does not interleave with streaming output; a
live-updating assistant message; distinct, labeled "mission update" entries; clean
scrollback; Ctrl+C to quit) WITHOUT gold-plating (no markdown rendering, tool-call cards,
status bar, or confirm affordance - those are a named later increment). Success = a bob you
launch (`bin/bob` / `bob tui`) that feels like a real chat client, with EVERY load-bearing
behavior of the current client preserved and every currently-green proof still green.

## In scope
Client-only change in `/Users/percules/dev/bob` (the `agent/`, `connector/`, session
protocol, and orchestration are untouched). Reuse the proven durable-session client
(`agent/lib/eve-session.ts`) as-is - ink only changes RENDERING and INPUT, not the transport.

- Rewrite `client/bob-tui.ts` as an `ink` app: add `ink` (+ `react`, `@types/react`) as deps;
  render the session's `StreamEvent`s through ink components instead of `process.stdout.write`.
  Keep the entry path `client/bob-tui.ts` (bin/bob's `BOB_TUI_ENTRY` default and the
  `bob:tui` script point at it) OR update both consistently if the entry file must change.
- Preserve ALL load-bearing behavior of the current client (read its header + body first,
  do not guess): attach to the ONE durable `bob:<host>` session; resume + REPLAY SCROLLBACK
  on relaunch (the `.bob-tui-session.<host>.json` sessionId cache shortcut, gitignored, never
  touching `.workflow-data`); dedup the human's own just-sent message so it is not re-rendered
  as an inbound event (`mySentTexts`); label a `message.received` with `bob-from:
  mission-relay` as a distinct "mission update" entry; skip history-replayed turns on live
  re-observe (the `isTurnResolved` logic). The durable-resume property (RFC S4 bet 1) MUST
  hold byte-for-byte behavior-identically through the new TUI.
- Rendering (functional-minimal, the whole point):
  - A live-updating assistant turn: `message.appended` deltas update the SAME rendered
    message in place (ink re-render), `message.completed` finalizes it - fixing today's
    unlabeled raw-delta writes.
  - A stable input box (ink `useInput`/`TextInput`) that never interleaves with streaming
    output (fixes the readline prompt-vs-`\n> ` interleave).
  - Finalized scrollback that stays put (ink `<Static>`), a live region for the in-flight
    turn; clear speaker labels (you / bob / mission update).
  - Ctrl+C quits cleanly.
- The confirm-gate flow rides ORDINARY turns (the gated tools return a challenge+token in
  their result and bob relays it as assistant text; the human types the token back as a
  normal message - it is NOT an `input.requested` event). v1 renders this as normal
  conversation; the human reads the challenge and types the token. A one-key "confirm"
  affordance is a RICH-tier extra - OUT of scope here, name it as the follow-up.
- The run/build story (a real toolchain decision - take a position): the project runs `.ts`
  directly via `node --experimental-strip-types`, which does NOT transpile JSX. Decide and
  implement one: (a) use ink WITHOUT JSX (`React.createElement`/`h`), staying
  strip-types-compatible and buildless; or (b) author `.tsx` and add a small build step
  (esbuild) producing a runnable client that `bin/bob` launches. Pick the one that keeps
  `bin/bob tui` a single command and does not regress startup. State the tradeoff.
- Keep the TUI-driven proofs GREEN: `proofs/lib/tui-driver.ts` spawns `client/bob-tui.ts` and
  asserts on its stdout (used by `proofs/confirm-gate-eve.ts` and the durable-resume claim,
  and the retired-from-acceptance `approval-tui.ts`). An ink app renders via ANSI redraws, not
  clean line output, so these WILL break unless handled. Provide a testable path: a headless/
  plain output mode for the client under test (e.g. `BOB_TUI_PLAIN=1` -> line output, or ink's
  test renderer), and update `tui-driver.ts` + the proofs' expectations so
  `proof:confirm-gate` and the durable-resume-through-the-TUI check pass against the ink
  client. This is load-bearing: those proofs are how we know the durable session + confirm
  flow still work through the front end.

## Non-goals
- NOT rich rendering: no markdown, no tool-call cards, no status bar (bob/eve/server state),
  no syntax highlighting, no one-key confirm affordance. All named as a later increment.
- NOT the packaging work (bob-cli RFC) - independent; this is client-only and lands separately.
- Do NOT change the session protocol, `agent/channels/bob.ts`, `agent/lib/eve-session.ts`'s
  transport, the connector, the confirm-gate tools, or any orchestration behavior. Rendering +
  input only.
- Do NOT port the DORMANT native-approval UI (`input.requested`/`approvalQueue`, kept for the
  eve #533 revert) into a rich ink affordance now; keep it minimal/behavior-preserved (a plain
  rendering is fine) so the #533 revert path is not broken, but do not invest in it.
- Do not regress durable resume, scrollback replay, the mission-update relay, or any green
  proof. No new dependencies beyond ink + react (+ their types).
- No em dashes. No entity/memory writes.

## Constraints
- Ground on the current client: READ `client/bob-tui.ts` fully (its long header documents
  exactly why it is a hand-built renderer over `eve-session.ts`, the resume/sessionId-cache
  mechanic, the mission-relay dedup, and the approval path) - preserve every one of those
  contracts. Reuse `agent/lib/eve-session.ts` (`sendHuman`, `streamSession`, `StreamEvent`,
  `waitForTurn`) unchanged.
- eve@0.22.1, Node >=24 baseline (unchanged). `bin/bob tui` must stay a single command.
- ink is ESM + React; keep the dependency addition tight (ink + react + @types/react only).
  Mind that this client ships in the bob package (bob-cli RFC) - do not balloon the install.
- Ships to a GitHub repo (`zico-io/bob`): the orchestrator bridges push + PR (`spawn.py
  bridge-pr bob-tui-ink`); agents prepare branch/commits + PR text, no gh/network in the clone.
- No em dashes; consistent vocabulary (bin/bob verbs, bob:<host> session, mission update,
  confirm-gate, StreamEvent kinds turn.started/message.appended/message.completed/
  message.received/input.requested).

## Acceptance criteria
- `client/bob-tui.ts` (or its consistently-updated entry) is an `ink` app; `bin/bob tui` and
  `npm run bob:tui` launch it as a single command with no added startup regression.
- Durable resume works through the ink TUI: launch, converse, kill, relaunch -> the SAME
  `bob:<host>` conversation resumes and scrollback replays (RFC S4 bet 1), verified by the
  durable-resume-through-the-TUI proof.
- Streaming assistant output updates in place with a clear `bob` label (no more raw unlabeled
  deltas); the input box never interleaves with streaming output; `mission update` relays are
  a distinct labeled entry; Ctrl+C quits cleanly.
- `proof:confirm-gate` (and the durable-resume TUI check) pass against the ink client via the
  provided headless/plain test path; `npm test` + the non-TUI proofs still green; typecheck
  clean; no em dashes.
- A short PR body prepared for the orchestrator to bridge to `zico-io/bob`.

## Affected areas
- `/Users/percules/dev/bob`: `client/bob-tui.ts` (rewritten as ink), `package.json` (ink +
  react deps, maybe a client build script + the `bob:tui` command), possibly `bin/bob`
  (`BOB_TUI_ENTRY` / launch), `proofs/lib/tui-driver.ts` + `proofs/confirm-gate-eve.ts` +
  the durable-resume TUI proof (updated for the ink client's test path), `.gitignore` (build
  output if a build step is added). New PR to `zico-io/bob`.
- Read for grounding (seeded by the orchestrator from the bob repo, since this mission's clone
  IS the bob repo): the current `client/bob-tui.ts`, `agent/lib/eve-session.ts`,
  `proofs/lib/tui-driver.ts`, `proofs/confirm-gate-eve.ts`, `bin/bob`, `docs/HOST-RUN-PLAYBOOK.md`.

## Risks and unknowns
- Testability is the sharpest risk: ink renders via ANSI/alternate-screen redraws, not clean
  line output, so the existing stdout-asserting proofs break by default. A headless/plain
  render mode (or ink's test renderer) is required so `proof:confirm-gate` + the durable-resume
  TUI check stay meaningful - design it before rewriting, not after.
- JSX vs strip-types: `node --experimental-strip-types` does not transpile JSX; either use ink
  without JSX (createElement, buildless) or add an esbuild step. The buildless path keeps
  `bin/bob tui` simplest but is more verbose; the build path is nicer to author but adds a
  step to the launch/package. Pick deliberately.
- Streaming re-render: `message.appended` deltas arriving rapidly must update in place without
  flicker or O(n) re-render cost; ink handles this but the live-region vs `<Static>` split
  must be right.
- Resume/scrollback fidelity: the current client replays history on attach via the sessionId
  cache; the ink version must reproduce that exactly (and still fall back correctly when the
  cache is absent) - a subtle behavior to preserve.
- Dependency weight: ink + react land in the bob package that the bob-cli RFC will ship; keep
  it lean and note the size delta for that downstream mission.

## Team plan
- repo: `/Users/percules/dev/bob`
- **tui-lead** (claude/opus): owns the ink app architecture (the StreamEvent -> component
  mapping, the live-region/`<Static>` split, the input model, resume/scrollback fidelity),
  the run/build decision (JSX vs createElement) and the `bin/bob tui` launch, integration, the
  headless test-path design, and the PR-body text. Fixes the app shape + the test path before
  workers diverge.
  - **worker-render** (claude/sonnet): the ink components + StreamEvent rendering - the
    live-updating assistant turn (`message.appended`/`message.completed`), the stable input
    box, the distinct `mission update` entry, speaker labels, scrollback via `<Static>`, and
    Ctrl+C - all preserving the current client's dedup/resume/mission-relay contracts.
  - **worker-proofs** (claude/sonnet): keep the TUI-driven proofs green against ink - implement
    the headless/plain render path, update `proofs/lib/tui-driver.ts` + `proofs/confirm-gate-eve.ts`
    + the durable-resume-through-the-TUI check to drive and assert on the ink client, and
    confirm `npm test` + the non-TUI proofs still pass. Authored here; the host-bound eve
    proofs are re-run by the orchestrator on the host.
