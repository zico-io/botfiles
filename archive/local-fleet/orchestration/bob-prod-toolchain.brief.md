# Mission brief: bob-prod-toolchain

Long name: "bob repo is still missing key production toolchains, like test coverage, professional user documentation, etc."

## Goal
Bob (`@zico/bob`, an npm-global orchestrator CLI at `/Users/percules/dev/bob`, GitHub
`zico-io/bob`) works but is not yet a production-grade open project: there is NO CI, coverage
is unmeasured, there is no lint/format config, and `docs/` holds only internal work artifacts
(PR bodies, spawn diffs, host-run sheets) - not user documentation. This mission adds the
missing production toolchains so bob reads and behaves like a real shipped product: a CI
pipeline that gates every push/PR, measured test coverage with a regression floor, a
lint/format setup, and a professional user documentation set for the npm-global `bob` CLI.
Success = CI is green on `main` and enforces typecheck + tests + coverage-floor + lint;
a fresh reader can install and run bob from the docs without reading source.

## In scope
Four toolchains, DECIDED with the human:

1. **CI pipeline (GitHub Actions)** - a `.github/workflows` that runs on push + PR against
   `zico-io/bob`: typecheck (`tsc`), the test suite, coverage (with the floor gate), and lint.
   Pin the Node version to the repo's `engines` (`>=24`; the VM runs v24.18.0). This is the
   integrating deliverable - it wires the other three into an enforced gate.
2. **Test coverage tooling + gate** - add coverage measurement (default: `c8`, an
   already-viable choice for the bare `node --experimental-strip-types` runner) and a
   threshold gate. Ambition is TOOLING + GATE, not test-chasing: measure current coverage,
   set the floor at (or just below) today's number as a ratchet that blocks regressions - do
   NOT write large amounts of new tests to hit an aspirational %. Also harden the runner: the
   `test` script is one brittle 7-command `&&` chain today; replace it with something that
   runs all `test/*.test.ts`, reports pass/fail per file, and fails the job on any failure.
3. **Lint + format** - default: **Biome** (one dev dependency that does both format + lint;
   ponytail-preferred over the eslint+prettier+plugins stack). Add config, a `lint` +
   `format` script, and reformat/fix the existing tree to pass clean. This lands FIRST in the
   squad ordering because it reformats the whole tree (big diff) - CI wires the gate after.
4. **User documentation** - rewrite `README.md` as a clean product intro (what bob is, install,
   30-second quickstart) and add a `docs/` USER guide set: install + prerequisites, first-run
   (`bob init` / `bob login` / `bob doctor`), a full command reference for the `bob` verb
   surface, and troubleshooting. Keep the internal artifacts (PR bodies, spawn diffs) where
   they are or move them under `docs/internal/` - do not delete them, but they are not user
   docs. Verify the documented commands against the actual `bin/bob` verbs and `bob --help`.

## Non-goals
- No changes to bob's RUNTIME behavior. This is toolchain + docs only. Do not refactor
  `agent/`, `connector/`, `client/`, or the eve harness logic to chase testability.
- If a NEW test or the lint/format pass surfaces a real defect, FLAG it to the lead (who
  flags the orchestrator) - do not silently fix runtime bugs inside this mission.
- No test-runner migration (stay on bare `node --experimental-strip-types`; do NOT move to
  vitest/jest/node:test as a framework swap).
- No aspirational coverage target / no large new test suites.
- No hosted docs site / static-site generator - README + `docs/` markdown only.
- No release automation, versioning, or publish pipeline (separate concern; see the existing
  `bob-release-tooling` mission).
- No touching the native orchestration stack (herdr, orbal-net, spawn.py) - bob repo only.

## Constraints
- Target repo: `/Users/percules/dev/bob` (GitHub `zico-io/bob`), branch off `main`.
- Node `>=24` (v24.18.0), `type: module`, TypeScript run directly via
  `--experimental-strip-types` (no build step for tests). Pinned `eve@0.22.1`. `os: darwin`,
  `cpu: arm64` - CI runners must match or the note must say why a step is skipped on Linux.
- Prefer the fewest new dev dependencies. Biome (one) over eslint+prettier (many). `c8` for
  coverage. No new runtime dependencies.
- No em dashes anywhere in code, config, or docs; use a plain "-".
- Do not hand-edit auto-generated files (`package-lock.json`, `.output`, `dist`, `.eve`).
- GitHub bridging: spawned agents have NO `gh`/network and their clone's origin is a local
  mirror. The orchestrator bridges all live GitHub steps - push + PR via
  `spawn.py bridge-pr bob-prod-toolchain`, and any repo-settings/branch-protection changes.
  Agents PREPARE artifacts as files/text (the workflow YAML, a PR body under `docs/`) for the
  orchestrator to execute. CI only actually runs once the orchestrator pushes the branch.

## Acceptance criteria
- `.github/workflows/*.yml` exists and, on push/PR, runs: typecheck, tests, coverage-floor
  check, and lint - all as required gates. The YAML is valid and the job graph is sane by
  inspection (orchestrator confirms the first real run is green after bridging the push).
- `npm test` runs every `test/*.test.ts`, reports per-file pass/fail, and exits non-zero on
  any failure. The old 7-command `&&` chain is gone.
- `npm run` exposes a coverage command that reports a total %; the CI floor is set to today's
  measured number (documented in the PR body) and fails when coverage drops below it.
- Biome (or the chosen tool) config is present; `npm run lint` and `npm run format` exist and
  the whole tree passes `lint` clean.
- `README.md` is a product-quality intro; `docs/` contains a user guide set (install,
  first-run, command reference, troubleshooting) whose commands match the real `bin/bob`
  verbs. A reader can install and run bob without reading source.
- No runtime behavior changed; `git diff` on `agent/`/`connector/`/`client/` is limited to
  formatting from the lint pass (or empty).

## Affected areas
- NEW: `.github/workflows/` (CI), `biome.json` (or eslint/prettier configs), coverage config.
- `package.json` - `test`, `lint`, `format`, `coverage` scripts; `devDependencies` (biome, c8).
- `test/` - runner harness only (a small runner script or a glob-based `test` command); no
  new behavior tests beyond what's needed to keep the floor honest.
- `README.md` - rewrite. `docs/` - new user guide files; possibly a `docs/internal/` move.
- Whole tree - one formatting pass from the lint/format tool (expected large, mechanical diff).

## Risks and unknowns
- The formatting pass produces a huge diff that collides with every other edit. MITIGATION:
  the lint/format worker lands FIRST and alone; other work rebases onto the formatted tree.
- `--experimental-strip-types` + `c8` coverage instrumentation may not compose cleanly (source
  maps / TS stripping). If `c8` cannot instrument, fall back to node's built-in
  `--experimental-test-coverage` or report the blocker - do NOT switch the whole runner to a
  framework to get coverage.
- CI runs on GitHub-hosted runners (likely `macos-*` for darwin/arm64, or ubuntu with a note).
  Some proofs/tests may assume a local host (herdr socket, microsandbox, Vercel auth) and
  cannot run in CI - the runner must select only the CI-safe `test/*.test.ts` and the brief's
  test set, not the `proofs/` that need a live host. Name what is excluded and why.
- `bob --help` / verb surface must be read from source, not assumed, or docs will drift.

## Team plan
- **quality-lead** (claude/opus): owns the three gate toolchains (CI, coverage, lint/format)
  and their integration. Sequences the squad so the format pass lands before CI wiring.
  Prepares the workflow YAML + PR body for the orchestrator to bridge.
  - **worker-lint** (claude/sonnet): add Biome config + `lint`/`format` scripts; run the
    format pass so the whole tree is clean. Lands first. Flags any real bug the pass surfaces.
  - **worker-ci-coverage** (claude/sonnet): add `c8` coverage + the floor gate; harden the
    `npm test` runner (glob over `test/*.test.ts`, per-file pass/fail, non-zero on failure);
    author the `.github/workflows` CI YAML that gates typecheck + test + coverage-floor + lint.
    Rebases onto worker-lint's formatted tree.
- **docs-lead** (claude/opus): owns the user documentation - README rewrite + `docs/` user
  guide set. Verifies every documented command against `bin/bob` and `bob --help`.
  - **worker-docs** (claude/sonnet): write the README product intro + `docs/` install,
    first-run, command-reference, and troubleshooting pages; move internal artifacts under
    `docs/internal/` without deleting them.
