# Mission brief: bob-cli-jsbuild

Long name: "fix the bob-cli Increment 1 packaging bug the host acceptance caught: the package ships raw .ts run via `node --experimental-strip-types`, but Node REFUSES to strip types for .ts under node_modules (hard policy), so a global `npm i -g @zico/bob` install cannot run at all - bob init/up/tui all die with ERR_UNSUPPORTED_NODE_MODULES_TYPE_STRIPPING. Ship COMPILED JS for the CLI's own TS graph, rewire bin/bob + its spawned entrypoints to .js, and add an INSTALL-TREE proof (run bob from a node_modules-installed tree, not the repo) so this class of false-green can never merge again."

## Goal
Make the packaged `@zico/bob` actually RUN when installed. The bob-cli Increment 1 host
acceptance failed at the first command (`bob init`) with
`ERR_UNSUPPORTED_NODE_MODULES_TYPE_STRIPPING`: the package ships raw `.ts` (bin/bob's imports
`agent/lib/bob-config.ts`/`bob-init.ts`/`platform-binaries.ts`/`host-exec.ts`, and the
spawned `connector/main.ts` + `client/bob-tui.ts`) and runs them via `node
--experimental-strip-types`, but Node deliberately does NOT strip types for `.ts` under
`node_modules` (confirmed in `node --help`: "the node_modules folder") - and a global install
lives under `node_modules`. The in-VM verb tests ran bin/bob from the REPO tree (where
stripping IS allowed), a structural false-green. Fix: ship COMPILED JS for the CLI's own TS
graph (a release build step, the same "build at release, ship the output" pattern the RFC
already chose for the eve `.output`), rewire the entrypoints to run `.js`, and - the headline
deliverable - add an INSTALL-TREE proof that runs bob from a node_modules-installed tree so
this exact class of bug is caught in CI, not on a host. Success = `bob` runs from an installed
tree (no type-stripping error), the install-tree proof is green, and the darwin host
acceptance (which the orchestrator re-runs) gets past `bob init`.

## In scope
Build on the Increment 1 code (this clone is the bob repo at the `mission-bob-cli-build`
branch - PR #7's code). Fix the packaging only; do not re-open other RFC decisions.

- Compile the CLI's own TS graph to JS at release/pack time. The compile target is the code
  bin/bob loads/spawns DIRECTLY, plus its transitive imports:
  - bin/bob's imports: `agent/lib/bob-config.ts`, `bob-init.ts`, `platform-binaries.ts`,
    `host-exec.ts` (and anything they import).
  - the spawned entrypoints `connector/main.ts` and `client/bob-tui.ts` and THEIR transitive
    imports (e.g. `connector/{config,cursor,reconcile,orbal-stream,webhook,liveness}.ts`,
    `agent/lib/eve-session.ts`, `agent/lib/orbal-net.ts`).
  Choose and implement the mechanism (esbuild bundle-per-entry, or `tsc` tree emit) that
  yields Node-24 ESM-correct JS with explicit `.js` import specifiers; state the tradeoff.
  The eve agent (`agent/channels/*`, `agent/tools/*`, `agent/instructions.md`) is compiled
  INTO `.output` by `eve build` - do NOT recompile it here UNLESS the next item proves
  otherwise.
- RESOLVE the deeper risk FIRST (before assuming the scope): does `bob up` (`eve start`
  running the prebuilt `.output/server/index.mjs`) itself load any `agent/*.ts` at RUNTIME
  under node_modules? `.output/server/index.mjs` references paths - if the built server
  imports agent tools/channels/skills as `.ts` at runtime, those hit the SAME
  type-stripping wall once installed, and the fix must cover them too (or confirm eve bundles
  them and it does not). Determine this empirically from `.output` before scoping the compile
  set; report the finding.
- Rewire `bin/bob`: import the compiled `.js` (not `.ts`); spawn `node <compiled
  connector>.js` and `node <compiled client>.js` (drop `--experimental-strip-types` for the
  packaged entrypoints); `BOB_TUI_ENTRY` default points at the compiled client. Keep the verb
  state machine + darwin proc-control byte-behavior-identical.
- `package.json`: `files[]` ships the COMPILED output (e.g. `dist/`) - the package must not
  depend on raw `.ts` being type-strippable at runtime. Keep `bin`/`os`/`cpu`/`bundledDependencies`/
  `optionalDependencies` and the prebuilt `.output` + bundled `eve@0.22.1` unchanged. Update
  `scripts/check-pack.mjs` to assert the new (compiled) tarball layout.
- THE INSTALL-TREE PROOF (the deliverable that prevents recurrence - runs IN-VM): `npm pack`,
  place the tarball's contents under a real `node_modules/@zico/bob/` (extract the tarball
  into a temp `node_modules`, bypassing the os/cpu global-install gate - the type-stripping
  failure is platform-independent, so this proves the fix on Linux), then RUN bob's
  entrypoints FROM THAT TREE (`node node_modules/@zico/bob/bin/bob <verb>` for the verbs a
  headless host can run - e.g. a `--help`/`status`/dry parse, plus importing the compiled
  bob-config/bob-init/platform-binaries modules, and spawning the compiled connector/client)
  and ASSERT no `ERR_UNSUPPORTED_NODE_MODULES_TYPE_STRIPPING` and the JS executes. This is the
  test the repo-tree verb test could not be: it must FAIL on today's raw-.ts code and PASS on
  the compiled package. Keep the existing `npm test` + `check-pack` green.
- Update `bin-bob-verbs.test.ts` (or add to it) so the verb checks run against the COMPILED,
  node_modules-located package, not the repo tree.

## Non-goals
- The full darwin HOST acceptance (real AI Gateway key mint + microsandbox + durable TUI +
  restart/reinstall durability) is re-run by the ORCHESTRATOR on darwin after this lands -
  in-VM prove the node_modules-execution fix + the install-tree proof (platform-independent).
- Do NOT re-open or change other RFC/Increment-1 decisions: prebuilt `.output`,
  bundledDependencies (eve@0.22.1), state_dir survival, config.toml, `bob login` key mint,
  the microsandbox installer, the two-package shape, vendor/ + provenance. Only the
  ship-compiled-JS + rewire + the proof.
- Do NOT rewrite `client/bob-tui.ts`'s behavior - the concurrent `bob-tui-ink` mission owns
  it. This mission COMPILES whatever `client/bob-tui.ts` is; keep the compile step general so
  it compiles the ink client too once that lands (final reconciliation is the orchestrator's
  at merge).
- Not herdr, not a second platform, not a real-registry publish, not markdown/tool-cards.
- No em dashes. No entity/memory writes.

## Constraints
- Ground on Increment 1's code (in this clone) + the failure: bin/bob's `import ...ts`
  lines (59-60, 75-76) + the `spawnDetached("node", ["--experimental-strip-types", ...])`
  calls (lines ~352, ~389) + the `await import("../agent/lib/bob-init.ts")` (lines ~433/437)
  are the exact break points. Node's restriction is hard (no override flag - confirmed).
- eve@0.22.1 pinned, Node>=24, darwin-arm64 target. The compiled output must be ESM (the
  package is `"type": "module"` per Increment 1) with correct `.js` specifiers; the prebuilt
  `.output` stays as-is.
- CONCURRENCY: `bob-tui-ink` (rewriting client/bob-tui.ts) and PR #7 (Increment 1) are both in
  flight on the bob repo. This mission's diffs touch bin/bob, package.json, the build scripts,
  and the proofs - overlapping BOTH. Keep diffs scoped + clearly listed; the orchestrator does
  the 3-way reconciliation at merge (Increment 1 + ink client + this jsbuild fix). Do NOT
  resolve their files.
- Ships to `zico-io/bob`: the orchestrator bridges push + PR (reconciled onto PR #7's branch
  since this completes Increment 1); agents prepare branch/commits + PR text, no gh/network.
- No em dashes; consistent vocabulary (bin/bob verbs, .output, bundledDependencies, state_dir,
  bob init/login, install-tree, node_modules type-stripping).

## Acceptance criteria
- The install-tree proof exists and is green: `npm pack` -> extract under
  `node_modules/@zico/bob/` -> `node node_modules/@zico/bob/bin/bob <verbs>` runs with NO
  `ERR_UNSUPPORTED_NODE_MODULES_TYPE_STRIPPING`; the compiled bob-config/bob-init/
  platform-binaries import and the compiled connector/client spawn cleanly. The same proof
  demonstrably FAILS against the pre-fix raw-.ts package (evidence it would have caught the
  bug).
- `bin/bob` runs the compiled `.js` entrypoints (no `--experimental-strip-types` for packaged
  code); verbs + darwin proc-control behavior-identical.
- `package.json` `files[]` ships the compiled output; the prebuilt `.output` + bundled
  eve@0.22.1 unchanged; `check-pack.mjs` asserts the new layout.
- The eve-.output-loads-agent-.ts-at-runtime question is answered with evidence, and if it
  IS a problem, the fix covers it (or a clear reason it is not).
- `npm test` (existing suite) green; typecheck clean; no em dashes; the concurrency overlap
  (bin/bob, package.json, build scripts, proofs) is listed for orchestrator reconciliation.
- A PR body prepared, and an updated HOST run sheet note that the acceptance now gets past
  `bob init` (the orchestrator re-runs the full darwin acceptance).

## Affected areas
- `/Users/percules/dev/bob` (mission-bob-cli-build branch): a compile/build step (esbuild or
  tsc config + a pack/prepack script), the compiled output dir (`dist/`), `bin/bob` (import +
  spawn rewiring to .js), `package.json` (`files[]` -> compiled), `scripts/check-pack.mjs`
  (new layout), the install-tree proof (new, e.g. `proofs/install-tree.mjs` +
  `npm run proof:install-tree`), `test/bin-bob-verbs.test.ts` (run against the installed tree),
  `.gitignore` (dist/build artifacts). Possibly the eve-agent compile set IF the runtime probe
  requires it.
- Reference already in the clone (Increment 1 code + docs/HOST-RUN-SHEET-cli-increment1.md).
- Reconciled onto PR #7 (`zico-io/bob`) by the orchestrator.

## Risks and unknowns
- The transitive import graph is the correctness crux: EVERY `.ts` the packaged entrypoints
  reach must be compiled, or it breaks under node_modules at the first import that misses. The
  install-tree proof is what guarantees completeness - exercise the real entrypoints, not a
  subset.
- eve `.output` runtime .ts loading (the deeper risk): if `bob up`'s `eve start` loads
  `agent/*.ts` at runtime under node_modules, that is a SECOND type-stripping wall the in-VM
  install-tree proof may not reach (it needs the Gateway to boot eve). Resolve it empirically
  from `.output`; if unresolved in-VM, flag it explicitly for the orchestrator's host re-run.
- ESM `.js`-specifier correctness: Node ESM needs explicit extensions; the compiler + rewired
  imports must be consistent, or it fails at resolve time under node_modules.
- Concurrency 3-way merge (Increment 1 + ink client + this fix) on bin/bob + package.json:
  real; keep diffs minimal + listed, orchestrator reconciles.
- Do not regress state_dir survival / config / the verb state machine while rewiring bin/bob.

## Team plan
- repo: `/Users/percules/dev/bob` (on the `mission-bob-cli-build` branch - Increment 1's code)
- **fix-lead** (claude/opus): owns the compile strategy (esbuild-bundle-per-entry vs tsc-emit,
  and the exact compile set), RESOLVES the eve-.output-runtime-.ts probe FIRST, rewires
  `bin/bob` to run compiled `.js` (behavior-identical verbs + proc-control), integrates, and
  owns the concurrency reconciliation note + the PR body + the updated host-run-sheet note.
  Fixes the compile set + output layout before workers diverge.
  - **worker-build** (claude/sonnet): implement the compile/build step (the chosen
    esbuild/tsc config + a prepack/pack script producing the compiled `dist/`), rewire the
    imports/spawns to `.js`, update `package.json` `files[]` to ship compiled output, and
    update `scripts/check-pack.mjs` for the new tarball layout. Keeps the prebuilt `.output` +
    bundledDependencies untouched.
  - **worker-proof** (claude/sonnet): build the INSTALL-TREE proof (`npm pack` -> extract into
    a temp `node_modules/@zico/bob/` -> run bob's entrypoints from there, assert no
    type-stripping error + JS executes), PROVE it fails on the pre-fix raw-.ts package and
    passes on the compiled one, move `bin-bob-verbs.test.ts` to run against the installed tree,
    and confirm `npm test` stays green. This is the anti-false-green deliverable.
