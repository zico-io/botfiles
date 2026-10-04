# Mission brief: tui-chat-redesign

Long name: "claude inspired tui chat interface for bob. the current ui isn't sexy"

## Goal
Make `bob tui` look and feel like a first-class, Claude-Code-inspired chat interface instead
of the current bare scrollback. Today the Ink TUI (`client/tui/ink-app.ts`) renders a plain
`<Static>` history, a live streaming line, colored speaker labels, and a bottom input box -
functional but not sexy. Success = `bob tui` on a real TTY presents a polished, framed chat
UI: a status/header bar (host, connection, model), scrollable in-app history with
keybindings, a slash-command palette, a streaming spinner/"bob is thinking" affordance, and
collapsible tool-call blocks - all while the durable session behavior, the plain-renderer
path, and the CI gate stay green.

## In scope
- A **full visual + UX rework of the Ink path** (`client/tui/ink-app.ts` and new components):
  - A framed chat layout (bordered/rounded panels, deliberate spacing, dim secondary text).
  - A **header/status bar**: host identity (`bob:<host>`), connection state, model/agent label.
  - **Scrollable in-app history** with keybindings (page/line scroll, jump-to-latest),
    replacing sole reliance on the terminal's native scroll of Ink `<Static>`.
  - A **slash-command palette** (e.g. `/help`, `/quit`, and any existing commands) surfaced
    in-UI with hints.
  - A **streaming affordance**: an animated spinner / "bob is thinking..." while a turn is
    in flight, resolving cleanly to the finalized turn.
  - **Collapsible tool-call / system-trace blocks** (expand/collapse per block; view-local
    state, not a SessionModel change).
  - Refined speaker treatment (you / bob / mission update) consistent with the new frame.
- **Lift the buildless constraint for the SHIPPED TUI** (human decision): JSX is allowed and
  the shipped `bob tui` runs BUILT output. This reverses today's model where the client runs
  unbuilt under `node --experimental-strip-types`. Every launch path that today runs the raw
  `.ts` must move to the built (JSX-aware) path - see Risks for the recommended seam.
- Wire the new JSX pipeline through the toolchain: `scripts/build-cli.mjs` (esbuild JSX
  loader), `tsconfig.json` (`jsx` setting), Biome (lint `.tsx`), and keep `build:cli` green.
- Keep the **dev hot-reload loop** (`npm run tui:dev`, just merged) rendering the NEW app -
  it currently runs `node --watch --experimental-strip-types`, which cannot strip JSX, so it
  must be updated to the same JSX-aware run path.
- Expand the **dev fixture scene** (`client/tui/dev/fixture.ts`) to exercise the new states:
  a collapsed+expanded tool block, a long history that scrolls, the slash palette, the
  spinner mid-stream.
- Update the **docs note** and add a **changeset** (minor - user-facing UI change).

## Non-goals
- **No change to `SessionModel` contracts** (`client/tui/session-model.ts`): durable attach,
  resume/scrollback replay, dedup, resolved-turn skipping stay byte-for-byte. The redesign is
  presentation-layer; any new state (scroll offset, which blocks are collapsed) is view-local.
- **No rewrite of the two-renderer model.** The `BOB_TUI_PLAIN=1` plain renderer
  (`client/tui/plain-renderer.ts`) stays the byte-oriented contract the proofs assert. The
  redesign is the Ink path; do not make the plain path visually fancy. If a proof's asserted
  bytes must change, change them deliberately and say why in the PR.
- Not a protocol/agent change: no touching eve, the connector, orbal-net, herdr, or spawn.py.
- Not a new backend feature - purely the client's presentation and interaction.
- No mouse support unless it falls out for free; keyboard-first.

## Constraints
- Target repo: `/Users/percules/dev/bob` (GitHub `zico-io/bob`), branch off `main`.
- `main` is protected by the `protect-main` ruleset: PRs only, required `ci` check
  (macos-15/node24: typecheck + lint + test + coverage floor 78 + build:cli + changeset), and
  branches must be up to date. The work lands as a PR that must stay green.
- **Buildless LIFTED for the shipped TUI** (human decision): JSX + a build step for the
  client are allowed; the shipped `bob tui` may run built output. Keep the build fast and
  part of `build:cli`. New DEV deps are fine. Keep RUNTIME deps minimal - JSX itself adds
  none (compiles to `React.createElement`); justify any new runtime dep (e.g. ink-spinner).
- Ink needs raw-mode stdin (a real TTY). The plain path and the stdout-asserting TUI proofs
  (`proofs/lib/tui-driver.ts`, `npm run proof:approval-wire`) must keep passing.
- Coverage floor is 78%. A large new UI surface can drag it down - add tests or fixture-
  driven proofs as needed to hold the floor; do not lower it without saying why.
- No em dashes anywhere; use "-".
- GitHub bridging: spawned agents have NO `gh`/network and their clone's origin is a local
  mirror. The orchestrator bridges the push + PR (`spawn.py bridge-pr tui-chat-redesign`) and
  any settings; the agents PREPARE the branch + a PR body as files/text.

## Acceptance criteria
- `bob tui` on a real TTY renders the new Claude-inspired interface: framed layout, header/
  status bar, scrollable history with keybindings, slash-command palette, a streaming
  spinner, and collapsible tool-call blocks.
- The shipped path runs the BUILT (JSX) output; `bin/bob` launches it; `npm run tui:dev`
  renders the same new app hot-reloaded on save.
- Durable behavior intact: attach/resume/dedup unchanged; `npm run proof:approval-wire`
  (plain-renderer durable-resume + approve/deny) passes.
- Plain-renderer path still works; any deliberate proof-byte change is called out in the PR.
- CI green end to end: typecheck (JSX config), lint (Biome on `.tsx`), test, coverage >= 78,
  build:cli, changeset present (minor).
- The dev fixture scene exercises the new states (collapsible block, scrolling, palette,
  spinner). The dev build output stays git-ignored and out of the tarball (`check-pack`).
- The PR shows the result concretely (a PTY-captured render or before/after) and states which
  launch-path seam was chosen for JSX (build-on-run loader vs point-everything-at-dist).
- A short docs note documents the new UI and the JSX/build change to the client model.

## Affected areas
- `client/tui/ink-app.ts` - rewritten with JSX + new components; likely a new
  `client/tui/components/` (frame, status bar, history viewport, input box, slash palette,
  tool block, spinner).
- `client/bob-tui.ts` and `bin/bob` - launch the built (JSX) output.
- `scripts/build-cli.mjs` (esbuild JSX), `tsconfig.json` (`jsx`), Biome config (`.tsx`).
- `client/tui/dev/tui-dev.ts` + the `tui:dev` script - JSX-aware run/watch path.
- `client/tui/dev/fixture.ts` - new scene states.
- `proofs/lib/tui-driver.ts` + proofs - launch path update; plain-path byte contract stable.
- `package.json` scripts + (dev) deps, `.changeset/*.md`, docs.

## Risks and unknowns
- **The buildless reversal is the central risk.** Today the dev path, the `tui:dev` hot-
  reload harness, and the proofs all `node --experimental-strip-types` the raw `.ts`; that
  cannot strip JSX. SPIKE the launch-path seam first, time-boxed, and pick ONE:
  (a) an **esbuild import loader / register hook** that transforms JSX at load (keeps the
  strip-types-like DX, so `tui:dev` and proofs change minimally - RECOMMENDED lazy path), or
  (b) **point every launch path at a build/watch of `dist/`**. Do not land JSX until every
  run path (shipped, dev, proofs) is green under the chosen seam.
- **Scrollable in-app history** replaces Ink `<Static>`'s native terminal scroll with a
  managed viewport. `<Static>` exists specifically to avoid re-rendering/flicker on long
  histories - a viewport must not reintroduce flicker or O(history) re-render per keystroke.
  If a clean in-app scroll is too costly, keep `<Static>` scrollback and add keybindings that
  cooperate with it; state the tradeoff.
- **Collapsible tool blocks** need per-block UI state that does not exist in SessionModel -
  keep it view-local and additive; do not push view state into the model.
- **Coverage floor**: a big presentation layer is hard to unit-test through a TTY. Lean on
  the fixture harness + plain-path proofs to keep the floor; add targeted tests for any new
  pure logic (scroll math, palette filtering, collapse state).
- **Plain-vs-Ink drift**: both renderers read the same SessionModel; the redesign must not
  make the Ink path depend on data the plain path cannot supply, or the two will diverge.

## Team plan
- **tui-design-lead** (claude/opus): owns the redesign core - the JSX launch-path spike and
  toolchain wiring (build-cli/tsconfig/biome), the new Ink components (frame, status bar,
  scroll viewport, input, slash palette, spinner, collapsible tool blocks), and keeping the
  SessionModel contracts + plain-renderer parity intact. Prepares the branch + PR body.
  - **worker-tui** (claude/sonnet): owns the supporting surface - expand the dev fixture
    scene for the new states, update `tui:dev` + the proofs to the chosen JSX run path, keep
    `check-pack`/coverage green, write the docs note and the changeset, and capture the
    PTY render for the PR.
