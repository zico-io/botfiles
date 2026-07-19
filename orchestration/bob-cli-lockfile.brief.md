# Mission brief: bob-cli-lockfile

Long name: "fix the package-lock.json drift that makes `npm ci` fail in the bob repo: the
platform optionalDependency @zico/bob-darwin-arm64@0.1.0 is an unpublished registry version
spec, so npm cannot create a lock node for it and `npm ci`'s strict in-sync check errors
('Missing: @zico/bob-darwin-arm64@ from lock file'). Wire the local platform package as an npm
WORKSPACE so it resolves via a local link for dev/CI, keeps the 0.1.0 registry spec for the
real release, and lets `npm ci` succeed."

## Goal
`npm ci` currently fails in the bob repo, so the darwin host acceptance had to fall back to
`npm install` and CI cannot use the fast, reproducible `npm ci`. Fix the lockfile drift at its
root so a clean `npm ci` succeeds, WITHOUT changing how the real release resolves the platform
package (end users installing `@zico/bob` from the registry must still pull
`@zico/bob-darwin-arm64@0.1.0` from the registry). Success = `rm -rf node_modules && npm ci`
succeeds on a clean checkout; the shipped `0.1.0` optionalDependency spec is unchanged; pack /
install-tree / check-pack all stay green.

## Root cause (grounded on the host)
- `package.json` declares `optionalDependencies: { "@zico/bob-darwin-arm64": "0.1.0" }` - a
  REGISTRY version spec.
- The platform package is NOT published (`npm view @zico/bob-darwin-arm64` -> E404). npm cannot
  resolve `0.1.0` from the registry, so the lock has no package node for it.
- `npm install` SUCCEEDS anyway (the dep is optional, npm tolerates a missing optional) but the
  produced lock is still "out of sync" for `npm ci`, whose strict check errors: "Missing:
  @zico/bob-darwin-arm64@ from lock file". So regenerating the lock alone does NOT fix it - the
  dep has to actually RESOLVE.

## In scope (chosen approach: npm workspaces)
Build on `main`. Make `platform/darwin-arm64` an npm workspace of the root package:

- Add `"workspaces": ["platform/darwin-arm64"]` to the root `package.json`.
- Regenerate `package-lock.json` (`npm install`) so npm links the local workspace to satisfy
  the `@zico/bob-darwin-arm64@0.1.0` optionalDependency (name + version match) and records a
  `link: true` node - which puts the lock back IN SYNC so `npm ci` passes.
- Keep the `optionalDependencies: { "@zico/bob-darwin-arm64": "0.1.0" }` spec EXACTLY as is
  (registry version - the release still resolves it from npm; the `workspaces` field in a
  published dependency's package.json is ignored by consumers, so it is harmless in the
  shipped `@zico/bob`).

Why workspaces over the alternatives (state these in the PR so the choice is legible):
- `file:platform/darwin-arm64` spec - REJECTED: it changes the shipped dep from a registry
  version to a file path that does not exist on an end user's machine, breaking the real
  install.
- publish the platform package so `0.1.0` resolves - REJECTED: premature; this is a dev/CI
  lock fix, not a release.
- regenerate the lock and accept the missing optional - REJECTED: already the status quo,
  `npm ci` still fails.

## Non-goals
- Do NOT publish either package to the registry.
- Do NOT change the `0.1.0` optionalDependency version, the `os`/`cpu` gates,
  bundledDependencies, or the two-tarball global-install acceptance flow (`npm i -g` each
  tarball) - that path is tarball-based and independent of the dev-repo workspace wiring.
- Do NOT touch the bob-cli-hostfix2 code (login/eve/packageRoot) - lockfile + package.json
  workspace wiring only.
- No em dashes. No entity/memory writes.

## Constraints
- REGISTRY ACCESS IS ORCHESTRATOR-ONLY. Regenerating `package-lock.json` and running
  `npm ci`/`npm install` require the npm registry (network), which spawned agents do NOT have
  (their clone's origin is a local mirror, no network). So the lead AUTHORS the `package.json`
  `workspaces` edit + the PR body + the run-sheet/CI note + the verification checklist; the
  ORCHESTRATOR executes the network-bound steps (regenerate the lock, `npm ci` clean-room
  verify, re-run pack/install-tree/check-pack) and bridges push + PR. Treat the lock
  regeneration exactly like the GitHub bridge: prepared by the agent, executed by the
  orchestrator. Never hand-edit `package-lock.json` (regenerate it via `npm install`).
- eve@0.22.1, Node>=24, darwin-arm64. The repo root IS the `@zico/bob` package.
- Ships to `zico-io/bob`: orchestrator bridges push + PR; the agent prepares files/text.

## Acceptance criteria (orchestrator-executed, on the darwin host)
- `rm -rf node_modules package-lock.json && npm install` produces a lock that includes a node
  for `@zico/bob-darwin-arm64` (a workspace `link`), then `rm -rf node_modules && npm ci`
  SUCCEEDS (the current failure is gone).
- `optionalDependencies["@zico/bob-darwin-arm64"]` is still `"0.1.0"` (unchanged registry
  spec); the published `@zico/bob` is unaffected (workspaces field ignored by consumers).
- No regression: `npx tsc` clean, full `npm test` green, `node scripts/check-pack.mjs` green
  (tarball still ships bin/agent/connector/client/.output/.eve/compile/vendor/dist),
  `npm run proof:install-tree` green, and `npm pack` still bundles the bundledDependencies
  (eve/ai/@vercel/connect/zod).
- A PR body explaining the workspace choice + the rejected alternatives, and a one-line CI
  note (CI can now use `npm ci`).

## Affected areas
- `/Users/percules/dev/bob` (main): `package.json` (add `workspaces`), `package-lock.json`
  (regenerated by the orchestrator, not hand-edited), possibly a short note in
  `docs/HOST-RUN-SHEET-cli-increment1.md` (npm ci now works - drop the `npm install`
  fallback) and/or a CI doc. New PR to `zico-io/bob`.

## Risks and unknowns
- Workspace hoisting: npm workspaces hoist deps to the root `node_modules`. Since the repo
  root already IS `@zico/bob` and the platform package has NO dependencies of its own (just a
  vendored binary), hoisting should not move eve/ai/zod - but the orchestrator MUST re-verify
  `npm pack` still bundles bundledDependencies and the install-tree proof stays green after the
  lock regen (that is the real regression surface).
- Confirm the `workspaces` field does not alter the packed tarball (check-pack top-level
  layout) - it should not, but verify.
- Make sure the platform package's own `package.json` name/version (`@zico/bob-darwin-arm64`
  `0.1.0`) exactly matches the optionalDependency spec so the workspace link satisfies it.

## Team plan
- repo: `/Users/percules/dev/bob` (on `main`)
- **lockfile-lead** (claude/sonnet): a single-agent team (no workers - this is a leaf-sized,
  well-specified fix). Authors the `package.json` `workspaces` edit, the PR body (workspace
  choice + rejected alternatives), the run-sheet/CI note, and a precise verification checklist
  for the orchestrator to run (the clean-room `npm ci`, the pack/install-tree/check-pack
  re-verify). Does NOT run the network-bound npm steps - flags them for the orchestrator, who
  regenerates the lock, verifies, and bridges the PR.
