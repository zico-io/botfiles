# Mission brief: bob-cli-hostfix

Long name: "fix the two packaging bugs the darwin host acceptance caught after the type-stripping fix landed: (A) packageRoot() resolves one directory too high (returns .../@zico not .../@zico/bob) so a globally-installed bob mis-detects its own .output/dist/vendor and `bob up` fails with 'prebuilt .output missing'; (B) `bob login`'s key-mint output parser expects id:/secret: key-value pairs but vercel CLI 54.18.1 prints the secret as a bare first line + `> Success! API key <name> (<id>) created`, so it stores an empty key. AND strengthen the install-tree proof so BOTH would have been caught in-VM: invoke bob through a real npm-bin SYMLINK (not the direct path) and include a stub .output so `bob up`'s detection runs."

## Goal
The bob-cli type-stripping fix is validated on darwin (`bob init` now runs). The full
real-install acceptance then caught two more packaging bugs that block a working `bob`, both
invisible in-VM. Fix both, and - the headline deliverable - STRENGTHEN the install-tree proof
so this class of "passes in-VM, breaks on a real global install" bug is caught in CI, not on
a host. Success = a globally-installed `bob` resolves its own package assets correctly and
`bob login` stores a usable key from the real vercel CLI output; the strengthened install-tree
proof is green (and demonstrably RED on the pre-fix code); the orchestrator's darwin re-run
gets `bob up` to boot eve.

## In scope
Build on `main` (this clone is the bob repo at `main` - increment 1 + the jsbuild fix + the
ink TUI are all merged). Fix packaging only; do not re-open other decisions.

- BUG A - `packageRoot()` resolves one directory too high. Evidence (darwin): the global bin
  is a symlink (`{prefix}/bin/bob` -> `.../node_modules/@zico/bob/bin/bob`); run via that
  symlink, `packageRoot()` returns `.../node_modules/@zico` (missing the `/bob`), so
  `path.join(ROOT, ".output", "server", "index.mjs")` misses - the real `.output` is at
  `.../@zico/bob/.output`. Result: `bob up` prints "prebuilt .output missing from the package".
  Every ROOT-relative path (`.output`, `dist/connector`, `dist/client`, `vendor/`, and the
  `.workflow-data` symlink target) is affected. FIX: resolve the TRUE package root robustly -
  anchor on the nearest `package.json` above the module (walk up from the compiled module's own
  location), or realpath the entry and derive a fixed, dist-aware level - so it is correct BOTH
  (1) when invoked via the npm bin symlink and (2) from the compiled `dist/` location (the
  jsbuild move to `dist/agent/lib/` is part of why the level math went wrong). Re-verify ALL
  ROOT-relative paths resolve after the fix.
- BUG B - `bob login` key-mint output parser. Current `parseMintOutput` (agent/lib/bob-init.ts)
  uses `/\bid\b\s*[:=]\s*.../` and `/\b(token|secret|key)\b\s*[:=]\s*.../` - it expects
  `id: X` / `secret: X` key-value pairs. The REAL `vercel ai-gateway api-keys create` output
  (CLI 54.18.1) is: the SECRET printed as a bare FIRST line, then the banner, then
  `> Success! API key <name> (<id>) created` (the id in parentheses). So the parser matches
  nothing and stores an empty key. FIX: parse the real format - secret = the bare first
  non-empty line (before the `Vercel CLI` banner); id = the parenthesized value in the
  `Success! API key <name> (<id>) created` line. PREFER a machine-readable path if one exists:
  check whether `vercel ai-gateway api-keys create` supports a `--json`/machine-output flag and
  parse that instead of scraping human text (more robust to CLI churn). Add a unit test with
  the exact real output shape as a fixture.
- STRENGTHEN the install-tree proof (proofs/install-tree.mjs) so both bugs are caught in-VM:
  1. Invoke bob through a REAL bin SYMLINK, exactly as `npm i -g` creates it (e.g. `npm link`
     the packed package, or create `{tmp}/bin/bob -> {tmp}/node_modules/@zico/bob/bin/bob` and
     run THAT), NOT the direct `node node_modules/@zico/bob/bin/bob` path the current proof
     uses - so `packageRoot()`'s symlink resolution is exercised (this is why bug A slipped
     through).
  2. Include a STUB `.output/server/index.mjs` in the packed/installed tree (a minimal file
     that just needs to EXIST) so `bob up`'s `.output` detection RUNS and asserts it is found -
     proving `packageRoot()` points at the real package root. The stub need not boot eve (that
     needs KVM + the Gateway - the orchestrator's darwin re-run); assert detection + path
     resolution only (e.g. `bob up` gets past the ".output missing" guard, or a dedicated
     path-resolution assertion).
  The strengthened proof MUST fail on the pre-fix code (bug A) and pass after; keep the
  existing type-stripping RED/GREEN coverage.

## Non-goals
- Do NOT try to boot eve / make real model calls in-VM (no KVM/Gateway) - the orchestrator
  re-runs the real darwin acceptance (bob up boots eve with a real key + the codeword-survives-
  restart durability) after this lands.
- The orphaned-key problem (the vercel CLI is create-only - no `ls`/`delete`) + the key's ORG
  identity (RFC open Q#3) + a spend budget (Q#8): FLAG these as follow-ups. If the parser fix
  moves to the Vercel REST API (which DOES support delete), note that as the robust path but do
  not build a full key-management surface here; the minimal fix is a correct parser.
- Do NOT re-open the type-stripping fix (done), the eve `.output` bundle, bundledDependencies,
  state_dir/config, or the ink client. packaging-resolution + key-parse + the proof only.
- No em dashes. No entity/memory writes.

## Constraints
- Ground on the darwin findings (this brief) + the code: `bin/bob` ROOT usage (lines ~62,
  75-76, 315, 414 - `.output`/`dist`/`vendor` are ROOT-relative), `packageRoot()` in
  `agent/lib/bob-config.ts`, `platform-binaries.ts` (also resolves package-relative paths -
  verify it is not affected by the same root bug), `parseMintOutput` in `agent/lib/bob-init.ts`,
  and `proofs/install-tree.mjs`. The compile step (`scripts/build-cli.mjs`, esbuild ->
  `dist/`) is the reason modules live at `dist/agent/lib/` at runtime - the root resolution
  must be correct for that compiled location.
- eve@0.22.1, Node>=24, darwin-arm64, ESM. Any dep resolves at runtime from node_modules
  (packages:external in build-cli.mjs - do not change).
- Ships to `zico-io/bob`: the orchestrator bridges push + PR; agents prepare branch/commits +
  PR text, no gh/network.
- No em dashes; consistent vocabulary (packageRoot, .output, dist, vendor, bob login,
  AI_GATEWAY_API_KEY, install-tree, npm bin symlink).

## Acceptance criteria
- `packageRoot()` returns the true package root (`.../@zico/bob`) BOTH via the npm bin symlink
  AND from the compiled `dist/` location; `bob up`'s `.output` check passes with a present
  `.output`; all ROOT-relative paths (dist/connector, dist/client, vendor, .workflow-data
  symlink) verified correct.
- `parseMintOutput` parses the real vercel CLI 54.18.1 output (secret = bare first line; id =
  parenthesized in the `Success! API key <name> (<id>) created` line), storing a non-empty
  key + id; unit-tested with the real-output fixture; a machine-readable flag is used if the
  CLI supports one (noted either way).
- The strengthened `proofs/install-tree.mjs` invokes bob via a REAL bin symlink and includes a
  stub `.output`, asserting `.output` detection passes (packageRoot correct); it FAILS on the
  pre-fix code and PASSES after (both RED/GREEN transcripts captured); the type-stripping
  RED/GREEN coverage is retained; `npm test` green; typecheck clean; no em dashes.
- A PR body + an updated host-run-sheet note (the darwin re-run now expects `bob up` to boot
  eve; the orphaned-key/org-identity/delete items flagged).

## Affected areas
- `/Users/percules/dev/bob` (main): `agent/lib/bob-config.ts` (`packageRoot()`), possibly
  `agent/lib/platform-binaries.ts` (same-root verify), `agent/lib/bob-init.ts`
  (`parseMintOutput` + maybe a `--json` mint path), `bin/bob` (if ROOT wiring needs it),
  `proofs/install-tree.mjs` (symlink invocation + stub `.output`), a new parser unit test,
  `docs/HOST-RUN-SHEET-cli-increment1.md` (note the re-run expectation + flags). New PR to
  `zico-io/bob`.
- Reference already in the clone (the merged code + docs).

## Risks and unknowns
- packageRoot correctness across contexts is the crux: it must be right via the symlink, from
  `dist/`, and when run directly (the existing proof path) - anchor on `package.json` is the
  most robust; verify all three. Do not regress the direct-run path the current proof uses.
- The vercel CLI output format is what it is TODAY (54.18.1) and may churn - a `--json` flag,
  if it exists, is far more robust than scraping; check for it first. If scraping, make the
  parser tolerant (the secret line may or may not be first depending on flags).
- The stub `.output` in the proof must not be mistaken for a real boot test - assert ONLY
  detection/path resolution; the real eve boot stays the darwin re-run.
- Do not regress the type-stripping fix or the state_dir symlink while touching ROOT
  resolution (the `.workflow-data` symlink target is ROOT-relative - re-verify it).

## Team plan
- repo: `/Users/percules/dev/bob` (on `main`)
- **fix-lead** (claude/opus): owns the root-resolution design (anchor-on-package.json vs
  realpath+levels) and the bin/bob wiring, integrates both fixes, owns the STRENGTHENED
  install-tree proof (symlink invocation + stub `.output`, RED-on-pre-fix/GREEN-after), the
  host-run-sheet update + PR body. Fixes the packageRoot contract before workers diverge.
  - **worker-root** (claude/sonnet): fix `packageRoot()` to resolve the true package root
    (symlink-safe + dist-aware), verify EVERY ROOT-relative path (`.output`, `dist/connector`,
    `dist/client`, `vendor/`, `.workflow-data` symlink) resolves via a symlinked install, and
    build the symlink+stub-`.output` half of the strengthened proof (drive bob through a real
    bin symlink, assert `.output` detection passes).
  - **worker-login** (claude/sonnet): fix `parseMintOutput` to parse the real vercel CLI
    54.18.1 output (secret = bare first line; id = parenthesized in the `Success` line); check
    for and prefer a `--json`/machine-readable create flag; add a unit test with the real-output
    fixture; keep the designed failure UX for genuine mint/parse failures.
