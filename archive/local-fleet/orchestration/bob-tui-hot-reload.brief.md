# Mission brief: bob-tui-hot-reload

Long name: "set up hot reload for tinkering on the bob tui"

## Goal
Make iterating on bob's terminal UI fast. Today the only way to see a TUI change is to run
the whole stack (`bob up`: orbal-net server + eve :3000 + connector) and `bob tui`-attach to
a live durable `bob:<host>` session, then restart by hand on every edit. That is a slow,
heavy loop for pure layout/component tinkering. Success = a maintainer runs one dev command,
the Ink TUI renders against canned session data with NO stack running, and editing a
component under `client/tui/` reflects in the running TUI within ~1-2s while preserving the
rendered session view - so you can tune the UI in a tight loop.

## In scope
- A **dev harness** that renders the real Ink app (`client/tui/ink-app.ts`) against a
  **mock/fixture SessionModel** - canned turns/events, labeled speakers, an in-flight
  streaming turn, mission-relay lines - with no orbal-net server, eve, or connector running.
- A **hot-reload loop**: on save to `client/tui/**`, the running TUI updates. Two tiers,
  ship whichever the spike proves:
  1. **State-preserving live refresh (target):** React fast-refresh style - swap components
     in place, keep component-local state (scroll position, input buffer). This is why the
     buildless constraint is lifted (see Constraints) - a dev build toolchain (esbuild/Vite +
     react-refresh, JSX allowed in dev) is permitted to achieve it.
  2. **Fast restart + fixture rehydration (guaranteed fallback):** `node --watch` restarts
     the harness on save; because the data is a deterministic fixture, the SessionModel
     rehydrates to the same view instantly, so a restart already reads as state-preserving.
     Ship this if tier 1 is not feasible for a terminal Ink app.
- A small, well-named dev entry (e.g. `client/tui/dev/`) holding the harness + fixtures.
- A documented `npm run` script (e.g. `tui:dev`) and a short docs note on the dev loop.
- Whatever minimal seam in `client/tui/session-model.ts` is needed to INJECT a mock data
  source, without changing the production durable-attach path.

## Non-goals
- No change to the SHIPPED TUI behavior or the production run path. `bob tui`
  (bin/bob -> `dist/client/bob-tui.js`, and `node --experimental-strip-types
  client/bob-tui.ts`) must keep working exactly as today. Lifting the buildless constraint
  applies to DEV tooling only - do not make the shipped client require a build.
- No rewrite of the two-renderer model. The mock harness feeds the SAME `SessionModel` the
  real app uses, so `ink-app.ts` and `plain-renderer.ts` cannot drift.
- Not a new production feature, not a test-runner change, not a release step.
- No touching the orchestration stack (herdr, orbal-net, spawn.py) or the eve agent.

## Constraints
- Target repo: `/Users/percules/dev/bob` (GitHub `zico-io/bob`), branch off `main`.
- `main` is protected by the `protect-main` ruleset: PRs only, required `ci` check
  (macos-15/node24: typecheck + lint + test + coverage floor + build:cli + changeset), and
  branches must be up to date. So the work lands as a PR that must stay green.
- **Buildless constraint LIFTED for dev tooling** (human decision): a dev-only build/watch
  step (esbuild/Vite, react-refresh, JSX) is allowed. Keep it DEV-ONLY - it must not enter
  the shipped tarball (`files` list) or gate the production path. New DEV dependencies are
  fine; NO new runtime dependencies.
- Prefer native/minimal: Node 24 ships `node --watch`; use it for the fallback tier before
  reaching for a bundler. Only add a build toolchain if tier-1 fast-refresh needs it.
- Ink needs raw-mode stdin (a real TTY) - the dev harness runs on an interactive terminal,
  like the app. The `BOB_TUI_PLAIN=1` plain renderer path and the stdout-asserting TUI
  proofs (`proofs/lib/tui-driver.ts`) must keep passing.
- Add a changeset (`.changeset/*.md`) - the CI gate requires one. A dev-tooling-only change
  is a `patch` (or an empty changeset if it truly ships nothing user-facing).
- No em dashes anywhere; use "-".
- GitHub bridging: spawned agents have NO `gh`/network and their clone's origin is a local
  mirror. The orchestrator bridges the push + PR (`spawn.py bridge-pr bob-tui-hot-reload`)
  and any settings; the agent PREPARES the branch + a PR body as files/text.

## Acceptance criteria
- One documented dev command (e.g. `npm run tui:dev`) launches the Ink TUI against
  fixture data with NO stack up, on a real TTY.
- Editing a component under `client/tui/` and saving updates the running TUI within ~1-2s,
  preserving the rendered session view (fixture rehydration at minimum; component-local
  state preserved if tier-1 fast-refresh lands).
- The fixture SessionModel exercises the main render states: multiple finalized turns,
  labeled speakers, a live streaming turn, and a mission-relay line.
- `bob tui` production path unchanged; `npm test` (incl. the plain-renderer TUI proofs) and
  the full `ci` gate stay green. The dev build output is git-ignored and not in `files`.
- A short docs note (README or docs/) explains the dev loop and which tier shipped.
- The PR states plainly whether tier-1 fast-refresh or the tier-2 fallback was delivered,
  and why.

## Affected areas
- NEW: `client/tui/dev/` (dev entry + fixture SessionModel), a watch/build script under
  `scripts/`, `.gitignore` entry for any dev build output.
- `package.json` - a `tui:dev` script; dev-only devDependencies if tier-1 needs a bundler.
- `client/tui/session-model.ts` - possibly a small injection seam for the mock source
  (additive; must not change production behavior).
- Docs - a dev-loop note. A `.changeset/*.md`.

## Risks and unknowns
- **Tier-1 is the real unknown:** state-preserving React fast-refresh inside a terminal Ink
  app is not a well-trodden path (fast-refresh tooling targets the DOM/RN reconcilers, not
  Ink's). SPIKE it first, time-boxed; if it does not work cleanly, ship the tier-2
  fast-restart + fixture-rehydration loop, which meets the practical goal. Do not sink the
  whole mission into an unproven fast-refresh rabbit hole.
- The mock-injection seam must not perturb `session-model.ts`'s load-bearing contracts
  (durable attach, resume/scrollback, dedup, resolved-turn skipping). Keep the seam additive
  and covered by the existing model behavior.
- A dev build step must stay dev-only - verify it does not leak into the tarball
  (`node scripts/check-pack.mjs`) or the shipped `bob tui`.
- Node `--watch` restart on a raw-mode TTY app: confirm the terminal is left in a sane state
  across restarts (no stuck raw mode).

## Team plan
- **tui-dev-lead** (claude/opus): owns the whole mission solo - spike tier-1 fast-refresh
  (time-boxed), build the fixture SessionModel + dev harness, wire the `tui:dev` script and
  (if needed) the dev build/watch, keep the shipped path + proofs green, write the docs note
  and the changeset, and prepare the branch + PR body for the orchestrator to bridge. No
  workers - it is a small, single-owner dev-ergonomics task.
