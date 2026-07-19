# Mission brief: orbal-net-changelog

Feature slug: `orbal-net-changelog` (mission room `mission-orbal-net-changelog`).
Long name: "full release note and changelog automation for the orbal-net crate".

## Goal
Automate release notes and the changelog for the public `orbal-net` crate
(`github.com/zico-io/orbal-net`) using `release-plz`, replacing today's manual
`git tag v*` -> empty GitHub Release flow. Adopt Conventional Commits going forward so
notes group cleanly.

Success: pushing Conventional-Commit changes to `main` makes release-plz open/update a
"release PR" that bumps the `Cargo.toml` version and updates `CHANGELOG.md`; merging that
PR tags the version, publishes to crates.io, and creates a GitHub Release whose body is
grouped, non-empty release notes (Features / Fixes / ...). A commit-lint gate keeps PRs
conforming. All existing CI stays green and nothing double-publishes.

## In scope
- release-plz GitHub Action: a `release-plz` workflow on push to `main` with the two
  standard jobs - `release-pr` (open/update the version+changelog PR) and `release`
  (on merge: tag, `cargo publish`, create the GitHub Release with notes).
- Config: `release-plz.toml` (single-crate repo) + `cliff.toml` (git-cliff) mapping
  Conventional Commit types to Keep-a-Changelog sections.
- Reconcile with the existing `.github/workflows/ci.yml` tag jobs: retire the manual
  `publish` job (release-plz now publishes - avoid double-publish), and keep the
  cross-platform binary build (`release` job, ubuntu+macos, `action-gh-release`) so
  binaries still attach to the release release-plz creates.
- `CHANGELOG.md`: seed/backfill covering the existing `v0.1.0` baseline; forward releases
  auto-updated by release-plz. Set release-plz's baseline so it does not try to re-release
  0.1.0.
- Backfill the empty `v0.1.0` GitHub Release body with generated notes (one-time).
- Commit-lint gate: CI check enforcing Conventional Commits on PRs; must not block merge
  commits or existing history. Lead decides target (PR title vs per-commit) based on the
  merge strategy.
- `CONTRIBUTING.md` note documenting the Conventional Commits convention.

## Non-goals
- No feature/behavior changes to the CLI, server, or TUI - automation and docs only.
- Do NOT rewrite existing git history to Conventional Commits; the convention applies
  going forward, past commits stay as-is.
- Do NOT re-publish, yank, or change `orbal-net 0.1.0` on crates.io; automation targets
  the next version onward (backfilling the v0.1.0 *notes* is fine).
- No changes to the `.botfiles` repo - this mission is the `zico-io/orbal-net` repo only.
- No new runtime dependencies, no MSRV/toolchain change, no CLI-framework migration.
- Do NOT hand-bump the crate version once release-plz owns it.

## Constraints
- Target repo `github.com/zico-io/orbal-net` is not cloned locally yet - clone first;
  repo path set in the roster.
- Keep all existing CI green: fmt, clippy, test (ubuntu+macos), coverage, deny, build.
- crates.io publish is irreversible - the first automated publish is lead-gated after
  `cargo publish --dry-run` and a release-plz dry-run/`release-pr`-on-a-branch pass.
- release-plz's `release` job needs a token that can push to `main` and TRIGGER downstream
  workflows; the default `GITHUB_TOKEN` does NOT trigger new workflow runs from its
  pushed tag, so the binary-build `release` job won't fire off release-plz's tag without a
  PAT/app token (or the binaries must be built inside release-plz's own release job).
  This token is a human/authorized step - request it, do not self-authorize.
- `CARGO_REGISTRY_TOKEN` secret already exists (from the prior release mission).
- Keep deps minimal; `cargo deny check` stays green.
- Commit-lint must be advisory-friendly: green on conforming PRs, must not fail on
  historical/merge commits.

## Acceptance criteria
- release-plz workflow present; a `release-pr` run on a test change opens/updates a PR that
  correctly bumps `Cargo.toml` version and appends grouped entries to `CHANGELOG.md` from
  Conventional Commits.
- Merging the release PR tags the version, publishes to crates.io (first run lead-gated),
  and creates a GitHub Release with a non-empty, grouped body.
- Cross-platform binaries (ubuntu+macos) still attach to the auto-created release.
- `CHANGELOG.md` exists in Keep-a-Changelog style and covers the `v0.1.0` baseline; the
  v0.1.0 GitHub Release body is backfilled.
- Commit-lint gate is green on a conforming PR and red on a non-conforming one, and does
  not block merge commits.
- No double-publish: the old manual `publish` job is retired; all prior CI jobs still green.
- Verifiable dry runs pass before any real publish: `cargo publish --dry-run` clean and a
  release-plz `release-pr`/dry-run on a branch produces the expected diff.

## Affected areas
- `zico-io/orbal-net` repo only:
  - `.github/workflows/`: new `release-plz.yml` (or a job folded into `ci.yml`);
    retire the `publish` job in `ci.yml`; adapt the tag-triggered binary `release` job;
    commit-lint workflow/config.
  - `release-plz.toml`, `cliff.toml` (new).
  - `CHANGELOG.md` (new/backfilled), `CONTRIBUTING.md` (new/updated).
  - `Cargo.toml` `version` (managed by release-plz henceforth).

## Risks and unknowns
- Token/trigger wrinkle (central risk): a tag pushed with the default `GITHUB_TOKEN` does
  not trigger the binary-build workflow. Resolve via a PAT/app token for release-plz, or
  by building binaries inside release-plz's release job. Decide early; needs a human secret.
- Double-publish: release-plz and the existing `publish` job both `cargo publish` - one
  must be retired before any tag lands.
- Merge strategy vs commit-lint: if PRs squash-merge, the PR title is what lands - lint the
  PR title; if merge/rebase, lint commits. Lead picks based on repo settings.
- release-plz baseline: configure so it treats `0.1.0` as already released and does not try
  to re-cut it; verify the first release PR proposes the correct next version.
- Repo not cloned locally; needs clone + push/PR access (authorized).
- release-plz single-crate config nuances (changelog path, git-cliff wiring, release PR
  labels/branch) - verify against release-plz docs, not memory.

## Team plan
- release-lead (claude/opus): owns the release-plz integration contract and sequences the
  work. Reconciles the new pipeline with the existing tag-triggered `publish`/`release`
  jobs (retire double-publish, keep binary attach), decides the commit-lint target
  (PR title vs commits) and the token strategy, gates the first irreversible crates.io
  publish behind dry-runs, and surfaces human-only steps (PAT/app-token secret, repo
  clone + push access). Owns the naming/section contract so the two workers do not diverge.
  - worker-pipeline (claude/sonnet): builds the automation. `release-plz.yml` workflow +
    `release-plz.toml`; retire the manual `publish` job; integrate the cross-platform
    binary build into the release release-plz creates; wire the token/trigger strategy the
    lead chose. Verifies with a `release-pr` run on a branch + `cargo publish --dry-run`
    before any real publish.
  - worker-changelog (claude/sonnet): owns changelog content + convention. `cliff.toml`
    grouping (Conventional Commits -> Keep-a-Changelog sections, per the lead's contract);
    seed/backfill `CHANGELOG.md` for the `v0.1.0` baseline; backfill the empty v0.1.0
    GitHub Release body; the commit-lint gate CI job + `CONTRIBUTING.md` Conventional
    Commits doc. Coordinates `cliff.toml` ownership with worker-pipeline (this worker owns
    its content/format; pipeline consumes it).
