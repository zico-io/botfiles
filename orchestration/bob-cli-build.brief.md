# Mission brief: bob-cli-build

Long name: "build Increment 1 of the bob-cli RFC - 'the package boots on one host'. Turn zico-io/bob into an installable @zico/bob npm package (+ the @zico/bob-darwin-arm64 platform package) that carries a node-ported bin/bob, the prebuilt eve .output + bundled eve@0.22.1, a vendored orbal-net binary + a vendored spawn.py snapshot, a ~/.config/bob/config.toml writer, durable state moved OUT of the package to ~/.local/state/bob (surviving npm update -g), and a bob init that writes config + runs bob login (mints a long-lived AI Gateway key, killing the OIDC re-link) + installs the microsandbox runtime. herdr, full bob-doctor drift-checks, and any second platform are OUT (later increments)."

## Goal
Build the smallest slice that proves the bob-cli RFC's thesis end to end on the proven
platform (darwin-arm64): a self-contained `@zico/bob` you install once and just run. This is
RFC Increment 1 - "the package boots on one host" (RFC S10). It deliberately does NOT include
the hard parts (herdr, full drift-checks, a second platform). Success = on a fresh
darwin-arm64 host with ZERO `.botfiles` clone, `npm i -g @zico/bob && bob init && bob` brings
up bob's durable TUI, a codeword survives `bob down`/`bob up` (durability now that state lives
in `state_dir`), and `vercel link` is NEVER run - proving the three highest-load-bearing RFC
decisions in one slice: state_dir survival, the OIDC-kill (long-lived AI Gateway key), and
prebuilt-boot. The real host acceptance is run by the ORCHESTRATOR on a darwin host (the build
VMs are Linux, no KVM/darwin); the fleet builds the package + validates everything testable
in-VM + delivers the host run sheet.

## In scope
Build into `/Users/percules/dev/bob`, per the bob-cli RFC (the design of record - PR #8,
seeded into the clone). Increment 1 only:

- Package structure (`@zico/bob`, RFC S3): make zico-io/bob a publishable npm package. Set
  `package.json` `name` `@zico/bob`, `bin: { "bob": "bin/bob" }`, `files` (bin, agent,
  connector, client, .output, vendor, package.json), `os:["darwin"]`, `cpu:["arm64"]`,
  `bundledDependencies` carrying eve@0.22.1's full resolved tree (so the exact tree the
  prebuilt .output was built against ships in the tarball + installs offline). Ship the
  PREBUILT `.output` (built at release time, shipped verbatim, never rebuilt on install - RFC
  S4). Do NOT modify the eve app's runtime behavior.
- The platform package `@zico/bob-darwin-arm64` (RFC S3/S5): a per-platform package
  (`os:["darwin"]`, `cpu:["arm64"]`, no `bin` field) carrying the vendored native binary.
  Increment 1 = `orbal-net` ONLY (its build path is known: `cargo install orbal-net` /
  the crate); herdr is DEFERRED to increment 2 (RFC open Q#2 - herdr has no build/release
  path). Wire `@zico/bob`'s optionalDependencies to select the platform package (esbuild
  pattern, RFC S5.2) and resolve the orbal-net binary path from it at runtime.
- Node-ported `bin/bob` (RFC S3): port today's bash `bin/bob` state machine
  (up/tui/status/down/server-down + default up+tui) to a node shebang entry that resolves
  package-relative paths (agent/, .output/, vendor/, the platform package's bin) instead of
  `cd "$(dirname "$0")/.."`, and reads `state_dir`/config instead of repo-relative paths.
  Behavior-identical verbs; the shared-server + connector lifecycle is unchanged.
- Durable state OUT of the package (RFC S10 #1, the riskiest decision - prove it HERE):
  `.workflow-data`, the orbal-net db/token, and logs move from repo-root to `state_dir`
  (default `~/.local/state/bob`, from config). This MUST survive `npm update -g` (which can
  replace the package's install tree) - the all-day durable session cannot be lost on update.
  Prove the state-outside-package property in this increment.
- Config writer (RFC S7.1): `bob init` writes `~/.config/bob/config.toml`
  (`BOB_HOST_IDENTITY`, `state_dir`, `orbal_net_port`, the vendored `ORCHESTRATION_DIR` ->
  `vendor/`, etc.), replacing every hand-exported env var; env > config > default precedence.
  `host-exec.ts`'s `orchestrationDir()` default becomes the package's `vendor/` (RFC S6/S7.1),
  and `vendor/` carries the pinned `spawn.py` + `plan_pane.py` snapshot + a `PROVENANCE` file
  (the source `.botfiles` commit SHA).
- `bob init` does exactly three things (RFC S10): (1) write the config; (2) run `bob login`
  to mint a LONG-LIVED AI Gateway API key (RFC S7.2 - `AI_GATEWAY_API_KEY`, killing the
  hourly `vercel link` re-link; the AI SDK precedence `AI_GATEWAY_API_KEY || VERCEL_OIDC_TOKEN`
  is cited) and store it in config/state; (3) run the microsandbox runtime installer
  (`install.microsandbox.dev`, RFC S5.4 - NOT the eve-dev-boot trick). Design the failure UX
  for each (esp. the microsandbox network fetch and the key mint).
- Validation + the host run sheet: in-VM prove everything KVM/darwin/Vercel-free (the package
  packs via `npm pack`; the tarball tree matches S3; `files`/`bin`/`os`/`cpu`/bundledDeps are
  correct; the config writer + state_dir separation logic via unit tests; host-exec resolves
  `vendor/`; bin/bob's node port parses its verbs). Deliver a HOST run sheet for the
  orchestrator: `npm pack` -> `npm i -g <tarball>` (a real global install, no registry needed
  for the proof) -> `bob init` (mint the key, install microsandbox) -> `bob` -> codeword
  survives `bob down`/`bob up` -> confirm no `vercel link` ran.

## Non-goals
- The real HOST acceptance (a fresh darwin-arm64 `npm i -g` + `bob init` minting a real AI
  Gateway key + `bob` + restart-durability) is run by the ORCHESTRATOR on a darwin host - it
  needs darwin + microsandbox + a Vercel login to mint the key, none of which the Linux build
  VM has. In-VM: build the package + validate structure/logic + author the host run sheet.
- OUT of increment 1 (later increments, per RFC S10): herdr (the second native binary +
  spawn a real fleet), full `bob doctor` drift-checks, a second platform (linux/etc.),
  publishing to a real registry (prove via `npm pack` + local `npm i -g <tarball>`; a real
  private-registry publish is a follow-up).
- OUT / deferred product calls (flag, do not decide): the AI Gateway key's ORG identity (RFC
  open Q#3 - mint under the current operator login for THIS proof; a team/bot Vercel identity
  is a follow-up) and a default spend budget on the key (RFC open Q#8). `gh` auth + Node>=24
  stay unmanaged host prerequisites (`init` may CHECK, never installs - RFC open Q#6).
- Do NOT change the eve app runtime, the session protocol, the connector, the confirm-gate,
  the orchestration behavior, or spawn.py's logic (vendor a SNAPSHOT; `.botfiles` stays home -
  RFC S6). Do NOT re-open any RFC decision.
- No em dashes. No entity/memory writes.

## Constraints
- Ground on the bob-cli RFC (PR #8 / seeded into the clone as `docs/reference/bob-cli.rfc.md`):
  S3 (package layout), S4 (prebuilt .output), S5 (native binaries + optionalDependencies),
  S6 (spawn.py vendor + provenance), S7 (config/creds/bob init/login), S8 (version lockstep),
  S10 (this increment). Follow its positions; do not invent alternatives.
- CONCURRENCY WARNING: the `bob-tui-ink` mission is modifying `client/bob-tui.ts` (an ink
  rewrite) IN THE SAME bob repo AT THE SAME TIME. This increment SHIPS `client/bob-tui.ts`
  as-is (it is `BOB_TUI_ENTRY`); do NOT modify it - the tui mission owns it. Your
  `package.json` + `bin/bob` changes WILL overlap theirs (both touch package.json deps /
  bin/bob); keep your diffs to those two files minimal + clearly scoped, and FLAG them for the
  orchestrator, who reconciles the two PRs at merge. Do not resolve their file for them.
- eve@0.22.1 pinned (bundledDependencies must carry exactly it), Node >=24, microsandbox
  backend (agent/sandbox.ts) - all consumed as givens. darwin-arm64 is the ONLY target.
- Ships to a GitHub repo (`zico-io/bob`): the orchestrator bridges push + PR (`spawn.py
  bridge-pr bob-cli-build`); agents prepare branch/commits + PR text, no gh/network in the
  clone.
- No em dashes; consistent vocabulary (bin/bob verbs, shared-server, state_dir, config.toml,
  bob init/login, vendor/, bundledDependencies, AI_GATEWAY_API_KEY, microsandbox).

## Acceptance criteria
- `npm pack` in the clone produces a `@zico/bob` tarball whose tree matches RFC S3 (bin/agent/
  connector/client/.output/vendor/package.json + the bundled eve tree); `package.json` has
  the right `name`/`bin`/`files`/`os`/`cpu`/`bundledDependencies`; the platform package
  `@zico/bob-darwin-arm64` carries the vendored `orbal-net` binary + correct `os`/`cpu`.
- `bin/bob` is a node entry with behavior-identical verbs (up/tui/status/down/server-down +
  default), resolving package-relative paths + `state_dir`/config (unit-verified in-VM).
- Durable state writes to `state_dir` (default `~/.local/state/bob`), NOT the package tree;
  the state-outside-package property is demonstrated (a state_dir with a session db is
  untouched by a simulated package-tree replacement).
- `bob init` writes `~/.config/bob/config.toml` (removing every hand-exported env var),
  and its three steps (config, `bob login` key-mint, microsandbox install) are implemented
  with a designed failure UX; `host-exec.ts` `orchestrationDir()` defaults to `vendor/`;
  `vendor/` has `spawn.py` + `plan_pane.py` + `PROVENANCE` (a real `.botfiles` SHA).
- A HOST run sheet the orchestrator runs on darwin: `npm pack` -> `npm i -g <tarball>` ->
  `bob init` -> `bob` -> codeword survives `bob down`/`bob up` -> no `vercel link`. In-VM
  unit/structure validation green; typecheck clean; no em dashes.
- A PR body prepared for the orchestrator to bridge to `zico-io/bob`, and a clear note of the
  `package.json`/`bin/bob` overlap with the concurrent `bob-tui-ink` PR for reconciliation.

## Affected areas
- `/Users/percules/dev/bob`: `package.json` (publishable @zico/bob + optionalDependencies +
  bundledDependencies + files/bin/os/cpu), a new `@zico/bob-darwin-arm64` platform package
  (layout + the vendored orbal-net binary), `bin/bob` (bash -> node port), `agent/lib/host-exec.ts`
  (`orchestrationDir()` default -> vendor/), new `vendor/` (spawn.py + plan_pane.py + PROVENANCE),
  a config writer + `state_dir` logic (new lib + `bob init`/`bob login` wiring), `.gitignore`
  (state paths), the release/pack scripts, unit tests, a host run sheet + PR body. SHIPS but does
  NOT modify `client/bob-tui.ts` (owned by the concurrent tui mission).
- Seeded reference (orchestrator adds; remove before final): `docs/reference/bob-cli.rfc.md`
  (the design of record), and the current `.botfiles` `orchestration/spawn.py` + `plan_pane.py`
  to vendor a snapshot of (with the source SHA for PROVENANCE).
- New PR to `zico-io/bob`.

## Risks and unknowns
- state_dir survival (RFC #1) is the riskiest single decision and the reason it is proven in
  increment 1: get the path/layout wrong and the all-day durable session is lost on the first
  `npm update -g`. Design + demonstrate the state-outside-package property explicitly, not by
  assertion.
- bob login / AI Gateway key mint (RFC S7.2 + open Q#7): minting a long-lived key needs the
  Vercel CLI or a REST call against a Vercel token (RFC leans REST). The exact mint mechanism
  + the token/credential the operator supplies is a real design point to settle here; the
  key's org-identity + budget are deferred product calls (flag, do not decide). The real mint
  is a HOST step the orchestrator runs.
- microsandbox installer (RFC S5.4): confirmed on paper, not from a real `bob init` run; the
  network-fetch failure UX is the single most likely first-run failure - design it, and the
  orchestrator validates it on the host.
- CONCURRENCY with `bob-tui-ink` on package.json/bin/bob: real merge overlap; keep diffs
  minimal, flag for orchestrator reconciliation, do not touch client/bob-tui.ts.
- Prebuilt `.output` in the tarball couples the package to a build target; the pack must
  capture the exact `.output` + bundled eve tree the release built, byte-for-byte (RFC S4).
- The node-port of `bin/bob` must not regress the darwin process control (the bash version's
  pgrep/kill path) or the shared-server lifecycle.

## Team plan
- repo: `/Users/percules/dev/bob`
- **cli-lead** (claude/opus): owns the package architecture + the increment-1 integration -
  the `bin/bob` bash->node port (behavior-identical verbs + package-relative + state_dir
  paths), the two-package (@zico/bob + platform) shape, the in-VM structure/logic validation,
  the HOST run sheet + PR body, and the concurrency coordination with the bob-tui-ink mission
  (flagging the package.json/bin/bob overlap). Fixes the package + state_dir shape before
  workers diverge.
  - **worker-pkg** (claude/sonnet): the npm packaging mechanics - `package.json` (@zico/bob:
    name/bin/files/os/cpu/bundledDependencies + optionalDependencies), the `@zico/bob-darwin-arm64`
    platform package + the vendored `orbal-net` binary + runtime path resolution, shipping the
    prebuilt `.output`, `vendor/` (the spawn.py/plan_pane.py snapshot + PROVENANCE SHA), and the
    `npm pack` structure check. Confirms the tarball tree matches RFC S3.
  - **worker-init** (claude/sonnet): the config + first-run wiring - the `~/.config/bob/config.toml`
    writer (killing every hand-exported env, env>config>default), the `state_dir` separation
    (state OUT of the package, survives an update, proven), `host-exec.ts` `orchestrationDir()`
    -> vendor/, and `bob init`'s three steps (config, `bob login` AI-Gateway-key mint per RFC
    S7.2 with a designed failure UX, microsandbox installer per S5.4) + their unit/in-VM tests.
