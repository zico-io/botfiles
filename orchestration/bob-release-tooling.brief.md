# Mission brief: bob-release-tooling

Long name: "set up changesets and production release tooling to the bob project"

## Goal
Give `@zico/bob` a real, repeatable release process. Today the bob repo
(`/Users/percules/dev/bob`, GitHub `zico-io/bob`) is at `0.1.0` with NO
`.changeset/` dir and NO `.github/workflows/` - versions are hand-bumped and there
is no changelog, no tags, no release artifacts. Success = a maintainer adds a
`changeset` per meaningful change, and cutting a release is a short, documented,
deterministic sequence that produces: a bumped `package.json`, an updated
`CHANGELOG.md`, a git tag, and a GitHub Release with the built `.tgz` bundle
attached. The first real release (baseline `v0.1.0`) ships as part of this mission.

## In scope
- Introduce `@changesets/cli`: `.changeset/config.json` + `.changeset/README`,
  `changeset`, `changeset:version`, `changeset:status` npm scripts, and an initial
  changeset for the baseline.
- Use changesets ONLY for version bump + `CHANGELOG.md` generation. It is NOT the
  publisher (see Constraints - distribution is GitHub Releases, not npm).
- CI validation gate: `.github/workflows/ci.yml` running on PRs - `npm ci`,
  `typecheck`, `test`, `build:cli`, and `changeset status` (fail a PR that changes
  shipped code but adds no changeset). Runner must be macOS/arm64 (see Risks).
- Release execution runbook + helper: the deterministic sequence to cut a release -
  `changeset version` -> commit -> `npm run build:cli` (produces
  `zico-bob-<ver>.tgz`) -> tag `v<ver>` -> GitHub Release with the `.tgz` attached
  and notes from the changelog. A thin script (e.g. `scripts/release.mjs`) that does
  the local/deterministic parts is fine; the network steps are the orchestrator's.
- `RELEASING.md` (+ a CONTRIBUTING pointer): how to add a changeset, what a release
  looks like end to end, who runs which step.
- Cut the first release: baseline `v0.1.0` of the current tree (tag + GitHub Release
  + attached `.tgz`), then changesets drives `0.1.1`+ from there.

## Non-goals
- NO npm-registry publishing. Do not add `changeset publish`, npm auth, NPM_TOKEN
  secrets, `publishConfig`, or `.npmrc`. Distribution is GitHub Releases only.
- Not a monorepo conversion - bob stays a single package; do not add workspaces or
  changeset's multi-package fixed/linked config.
- No changes to what the package builds or bundles (the eve app, native binaries,
  `build:cli`/`prepack` behavior) - only wrap a release process around it.
- No cross-platform build (linux/x64). Package stays `os: darwin`, `cpu: arm64`.
- No auto-publishing bot / no changesets "Version Packages" PR automation in v1
  (the version bump is a manual, orchestrator-run step). Note it as a future add.
- No signing/notarization of the bundle.

## Constraints
- Distribution = GitHub Releases only (decided): each version is a git tag `v<x.y.z>`
  + a GitHub Release carrying `CHANGELOG` notes and the built `.tgz`. Install is via
  the release URL, not a registry.
- Release model = manual / orchestrator-bridged (decided): agents PREPARE config,
  scripts, docs, and the changeset files; a human/orchestrator runs the version bump
  and the release. Spawned agents have no `gh`/network and their clone's origin is a
  local mirror - the orchestrator bridges every live GitHub step (push + PR via
  `spawn.py bridge-pr bob-release-tooling`, tag push, `gh release create`, repo
  settings). Agents must not assume they can reach GitHub or npm.
- Keep the existing `build:cli`/`prepack` bundle pipeline intact - the release just
  invokes it; do not rewrite it.
- Node 24, `type: module`. Follow the repo's existing script/style conventions.

## Acceptance criteria
- `npx changeset` works; `.changeset/config.json` present and valid for a single
  package with `access: restricted`/no-publish semantics (changelog-only use).
- `npm run changeset:version` bumps `package.json` and writes/updates `CHANGELOG.md`
  from pending changesets, with no attempt to hit npm.
- `.github/workflows/ci.yml` runs green on a PR (typecheck + test + `build:cli` on a
  macOS arm64 runner) and FAILS a PR that touches shipped code with no changeset.
- The release runbook, followed literally, produces: bumped version, updated
  changelog, `v<ver>` tag, and a GitHub Release with the `.tgz` attached. Dry-run the
  local/deterministic portion end to end (stop before the network steps, which the
  orchestrator executes).
- `RELEASING.md` is complete enough that a maintainer who has never released bob can
  cut one by following it.
- Baseline `v0.1.0` release is prepared (tag + release notes + `.tgz`) ready for the
  orchestrator to publish.
- `npm test` and `npm run typecheck` stay green.

## Affected areas
- New: `.changeset/` (config + initial changeset), `.github/workflows/ci.yml`,
  `RELEASING.md`, optional `scripts/release.mjs`.
- Edited: `package.json` (changeset scripts + `@changesets/cli` devDep;
  possibly a `CHANGELOG.md` seed), `README`/CONTRIBUTING pointer.
- Untouched: `agent/`, `connector/`, `client/`, `.output/`, `build:cli.mjs` bundle
  logic, the eve/native bundling.

## Risks and unknowns
- CI build on a platform-locked bundle: `build:cli` bundles darwin/arm64 native
  binaries + the eve `.output`. It likely only builds correctly on a macOS arm64
  runner (`macos-14`/`macos-15`). Confirm the gate can build there; if the full build
  is too heavy/slow for every PR, fall back to typecheck+test+`changeset status` on
  PRs and run `build:cli` only in the release step. Name the choice explicitly.
- First-version semantics: current tree is `0.1.0` and never released. Recommended:
  release the current tree AS `v0.1.0` (baseline, no bump), seed `CHANGELOG.md`
  with a "0.1.0 - initial release" entry, and let changesets drive `0.1.1`+
  afterward. Confirm before bumping to `0.1.1`.
- `.tgz` size (~37MB) on GitHub Releases is fine, but confirm the `files`/prepack
  output is the artifact we want to attach (the `zico-bob-<ver>.tgz` from
  `npm pack`/`build:cli`, not the raw repo).
- Changesets on a no-publish single package: ensure config does not try to
  `git tag`/publish on its own and does not choke without a registry.

## Team plan
- repo: `/Users/percules/dev/bob`
- release-lead (claude/opus): owns changesets setup (`.changeset/config.json`,
  scripts, initial baseline changeset), the versioning + `CHANGELOG` strategy,
  `RELEASING.md`, and the first-release (`v0.1.0`) cut plan. Integrates the worker's
  CI + release-script work and owns the final acceptance dry-run.
  - worker-ci (claude/sonnet): owns `.github/workflows/ci.yml` (macOS arm64 gate:
    typecheck + test + build + `changeset status`) and the deterministic release
    helper/runbook steps (`scripts/release.mjs`: version -> build tgz -> tag +
    release notes prepared for the orchestrator to push). Verifies the local portion
    runs green; hands the network steps to the orchestrator.
