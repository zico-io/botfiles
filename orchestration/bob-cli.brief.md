# Mission brief: bob-cli

Long name: "package bob into a proper installable CLI - kill the current dev-repo UX (clone the repo, cd in, hand-export env, run bin/bob, re-link Vercel every hour) and replace it with a self-contained npm-global `bob` you install once and just run: `npm i -g @zico/bob` -> `bob init` -> `bob`. Bundle everything bob needs (the eve L1 app + the orchestration stack: spawn.py, herdr, orbal-net + the microsandbox runtime) so one install brings a working orchestrator. Design RFC only, no shipped code."

## Goal
Produce a north-star packaging/distribution RFC (a written design doc, NO shipped code) for
turning bob from a dev-repo you run out of `/Users/percules/dev/bob` into a proper,
installable CLI. Today's UX is developer plumbing, not a product: you clone the repo, `cd`
into it, hand-export `BOB_HOST_IDENTITY`/`ORCHESTRATION_DIR`/`HERDR_ENV`, run `bin/bob`, and
re-run `vercel link` roughly every hour when the OIDC token expires; the orchestration stack
(spawn.py, herdr, orbal-net) and the microsandbox runtime are separate manual installs. The
target: `npm i -g @zico/bob`, then `bob init` (one-time config + dependency setup + login),
then `bob` - a durable all-day orchestrator on your PATH, no repo, no hand-exports, no hourly
re-link. Success = an RFC a lead could turn straight into a build mission, with concrete
positions on the package form, how a self-contained bundle ships the eve app + the native
orchestration binaries + spawn.py, the config/credentials/first-run UX, the CLI command
surface, and a migration path off the dev-repo workflow.

## In scope
DECIDED (do not re-open, settled with the human): npm-global distribution (`bob` bin on
PATH, runs on the host's Node - NOT a compiled standalone binary); BUNDLE-EVERYTHING (one
install brings bob + the orchestration stack, not "assume the herd is installed"); RFC/design
only. The RFC must take a concrete position on each of the following, not survey options:

- Package form + the eve-app bundle: how the npm package ships bob's eve L1 app (the `agent/`
  project, the `connector/`, and the built `.output` eve production server). Decide: ship a
  PREBUILT `.output` in the tarball vs build-on-postinstall (`eve build` needs the eve
  toolchain + is slow) - name the tradeoff and pick. Pin `eve@0.22.1` (the proven version)
  and state how the pin travels in the package.
- Bundling the NATIVE orchestration binaries (herdr, orbal-net): these are compiled binaries,
  not JS. Decide how they ship in an npm package - per-platform `optionalDependencies`,
  postinstall download of a pinned release, or vendored-in-tarball - and how versions are
  pinned + updated. Cover platform coverage (at minimum darwin-arm64, which is proven;
  say whether linux is in v1).
- Bundling spawn.py + the orchestration glue - and the SOURCE-OF-TRUTH question (the crux of
  "bundle everything"): spawn.py lives in and is actively developed in `.botfiles/orchestration`.
  Take a position: does bob become spawn.py's HOME (move it into the bob repo, .botfiles
  consumes it), or does the bob package VENDOR a pinned copy with a documented sync path? Name
  the drift risk and the ownership model either way. Same for `plan_pane.py` and any
  orchestration glue bob shells out to.
- The microsandbox runtime: the one-time `npx eve dev` libkrun install (~/.microsandbox) is a
  manual gotcha today. Design how `bob init`/`bob doctor` installs/verifies it automatically,
  and what happens on an unsupported host.
- Config + credentials UX (the actual pain): replace the hand-exported env
  (`BOB_HOST_IDENTITY`, `ORCHESTRATION_DIR`, `HERDR_ENV`, `ORBAL_NET_PORT`) with a config
  file (e.g. `~/.config/bob/config.toml`) written by `bob init`. Design the Vercel OIDC story
  to KILL the hourly re-link: `bob login` + auto-refresh (a longer-lived credential, a
  bob-managed refresh before expiry, or a clear re-auth prompt) - take a concrete position on
  what is actually possible with Vercel AI Gateway auth, grounded in current docs.
- CLI command surface: `bob` (up + attach TUI), `bob init`, `bob login`, `bob doctor`
  (checks/repairs deps + runtime + auth), `bob up`/`tui`/`status`/`down`/`server-down`
  (today's bin/bob verbs), and how mission-driving stays conversational in the TUI (the
  skills/tools are unchanged). Name what `bob init`/`doctor` check and auto-fix.
- First-run + migration: the exact `npm i -g` -> `bob init` -> `bob` flow for a fresh host,
  and the migration path for the current dev-repo user (map today's manual steps onto the new
  commands; what the bob repo's `bin/bob`/`HOST-RUN-PLAYBOOK.md` become).
- A ranked open-questions list + a recommended first build increment.

## Non-goals
- No shipped code, no prototype. Design and prose only.
- NOT a compiled standalone binary (bun/SEA) - npm-global is the decided form; mention a
  compiled binary only as a possible future, do not design it.
- NOT the remote/Vercel-deployed orchestrator (bob stays local-first, launched on the host).
- NOT re-designing the orchestration protocol, the 3-layer model, spawn.py's behavior, the
  shared-server model, or the confirm-gate - the CLI packages what exists, it does not
  re-architect it.
- NOT a rich-TUI rebuild. The thin stdout client is a known rough edge; the RFC may note
  whether it is acceptable for the packaged v1 and flag a proper TUI as a follow-up, but
  designing a new TUI is out of scope here.
- Does not re-open the eve #533 confirm-gate workaround or the microsandbox backend pin - it
  consumes both as givens.
- No entity or memory-fact writing.

## Constraints
- Ground on and reuse the proven, merged bob (zico-io/bob main): `bin/bob` (the launcher +
  its verbs + darwin/linux process control), `package.json` + the eve build, `agent/`,
  `connector/`, the `spawn_*`/`plan_pane_*`/`herdr_*` tools + `agent/lib/host-exec.ts` (which
  resolves `ORCHESTRATION_DIR`), `docs/HOST-RUN-PLAYBOOK.md` (the current manual flow this
  replaces), and `HOST-SHAKEDOWN.md`. Read the actual code, do not guess the current UX.
- eve is a Vercel beta; ground every eve/npm/Vercel-auth claim in current docs and flag
  beta/churn risk. Pin `eve@0.22.1`; the microsandbox backend (agent/sandbox.ts) + its
  one-time libkrun install are consumed as givens.
- The bundle must stay honest about what CAN and CANNOT live inside an npm package: JS/TS +
  prebuilt assets are easy; native binaries (herdr, orbal-net) and a VM runtime (microsandbox
  libkrun) are the hard part - the RFC must be concrete about the mechanism for each, not
  hand-wave "bundle it".
- No em dashes; use "-". Stay consistent with today's vocabulary (bin/bob verbs, shared
  orbal-net server, mission-<feature>/squad-<lead>, spawn.py up/down/poke/bridge-pr,
  confirm-gate, microsandbox).
- Deliverable is one markdown RFC committed to the `.botfiles` repo
  (`orchestration/bob-cli.rfc.md`), consistent with the other bob RFCs. Because it ships to a
  GitHub repo, the orchestrator bridges the push + PR (`spawn.py bridge-pr bob-cli`); agents
  have no gh/network and their clone origin is a local mirror - prepare the file, the
  orchestrator executes the GitHub step. Grounding files from the bob repo (which is NOT the
  mission clone) are seeded into the clone by the orchestrator.

## Acceptance criteria
- One self-contained RFC markdown (`orchestration/bob-cli.rfc.md`) readable cold by someone
  who knows neither bob nor eve.
- Every in-scope question answered with a concrete POSITION, not a menu.
- Contains, concretely: the npm package layout + the eve-app bundling decision (prebuilt
  vs build-on-install) with the tradeoff named; the native-binary (herdr/orbal-net)
  distribution mechanism + version pinning + platform coverage; a firm position on the
  spawn.py source-of-truth/ownership (bob-home vs vendor-with-sync) with the drift risk
  addressed; the microsandbox-runtime auto-install design; the config-file + `bob
  init`/`login`/`doctor` UX that removes every hand-exported env var; the OIDC-auto-refresh
  position (kills the hourly re-link) grounded in current Vercel docs; the full CLI command
  surface; the `npm i -g` -> `bob init` -> `bob` first-run flow + a migration path off the
  dev-repo; a ranked open-questions list; a recommended first build increment.
- Every eve/npm/Vercel-auth claim grounded in a cited current doc; beta/churn risks flagged.
- No factual conflict with the merged bob (bin/bob verbs, the shared-server model, the
  confirm-gate, the microsandbox pin). No em dashes.

## Affected areas
- New file only: `orchestration/bob-cli.rfc.md` (in `.botfiles`).
- Read (do NOT modify) for grounding, seeded into the clone by the orchestrator from the bob
  repo: `bin/bob`, `package.json`, the eve build scripts, `agent/lib/host-exec.ts`, the
  `spawn_*`/`plan_pane_*`/`herdr_*` tools, `docs/HOST-RUN-PLAYBOOK.md`, `HOST-SHAKEDOWN.md`,
  `agent/sandbox.ts`; plus `.botfiles` `orchestration/spawn.py`, `plan_pane.py`, `AGENTS.md`,
  and the eve / npm / Vercel AI Gateway auth docs.

## Risks and unknowns
- spawn.py source-of-truth is the load-bearing risk of "bundle everything": spawn.py is
  actively developed in `.botfiles` and shared with the current (claude) orchestrator path;
  bundling a copy into bob risks two diverging spawn.py's. The RFC must pick an ownership
  model (bob-home vs vendored-with-sync) and be honest about the cost.
- Native-binary + VM-runtime packaging: shipping herdr + orbal-net (compiled) and the
  microsandbox libkrun runtime through npm is the genuinely hard part; per-platform
  optionalDeps / postinstall-download each have failure modes (offline install, arch
  coverage, checksum/trust). Investigate what actually works before asserting.
- Vercel OIDC auth: the hourly-expiry re-link is the sharpest UX pain; whether a
  longer-lived or auto-refreshable credential exists for the AI Gateway is unknown - ground
  the answer in current Vercel docs and mark it if no clean refresh exists (then design the
  least-bad prompt).
- eve-app bundling: a prebuilt `.output` in the tarball is fast to install but couples the
  package to a build target + the microsandbox peer; build-on-postinstall is heavy/slow and
  needs the toolchain. The pick has real consequences - name them.
- Cross-platform: everything is proven on darwin-arm64 only; linux (and other arches) for the
  native binaries + microsandbox is unproven - be explicit about v1 platform scope.
- Update/versioning: npm handles bob's own updates, but the bundled binaries + the eve pin +
  spawn.py need a coherent version story so `npm update -g` does not desync them.

## Team plan
- repo: `/Users/percules/.botfiles`
- **rfc-lead** (claude/opus): owns the RFC end to end - immerses in the current bin/bob /
  HOST-RUN-PLAYBOOK UX and the merged bob, sets the thesis (a self-contained npm-global `bob`
  you install once and run), fixes the document outline + the package-layout + source-of-truth
  positions before workers diverge, integrates both workers' research into one coherent
  document, writes the migration path + the recommended first increment, and relays the
  human-only GitHub bridge steps.
  - **worker-packaging** (claude/sonnet): grounds the packaging mechanics - the npm package
    layout, the eve-app bundle (prebuilt `.output` vs build-on-install), the native-binary
    (herdr/orbal-net) distribution + pinning + platform coverage, the microsandbox libkrun
    auto-install, spawn.py vendoring mechanics, and the update/version story - all cited from
    current npm / eve / packaging docs. Produces the "how the self-contained bundle actually
    ships" half.
  - **worker-ux** (claude/sonnet): grounds the install/config/credentials UX - the config
    file replacing every hand-exported env var, the `bob init`/`login`/`doctor` command
    design + what they check/auto-fix, the Vercel OIDC auto-refresh position (grounded in
    current Vercel docs, to kill the hourly re-link), the full CLI command surface, the
    `npm i -g` -> first-run flow, and the migration path off the dev-repo. Produces the
    ranked open-questions/risks list.
