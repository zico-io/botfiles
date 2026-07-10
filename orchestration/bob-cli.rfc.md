# RFC: bob-cli - packaging bob into a self-contained, installable npm-global orchestrator

Status: draft
Owner: rfc-lead (mission bob-cli)
Scope: packaging / distribution design only. No shipped code, no prototype.

## 1. Summary and thesis

Today bob is a dev-repo you operate as raw plumbing. To stand up the L1 orchestrator you
clone `zico-io/bob`, `cd` into the clone, hand-export `BOB_HOST_IDENTITY`,
`ORCHESTRATION_DIR`, `HERDR_ENV`, and (optionally) `ORBAL_NET_PORT`, run `bin/bob`, and
re-run `vercel link` roughly every hour when the OIDC token expires. The orchestration
stack it drives - `spawn.py`, `herdr`, `orbal-net` - and the microsandbox libkrun runtime
are each a separate manual install. That is developer setup, not a product.

This RFC's thesis: bob ships as a single installable CLI on your PATH.

```
npm i -g @zico/bob      # one install brings bob + the whole orchestration stack
bob init                # one-time: config + dependency/runtime setup + login
bob                     # a durable all-day orchestrator - no repo, no hand-exports, no hourly re-link
```

The decided form (settled with the human, not re-opened here):

- npm-global distribution. `bob` is a bin on PATH that runs on the host's Node. NOT a
  compiled standalone binary (bun/SEA); a compiled binary is mentioned only as a possible
  future, never designed here.
- Bundle-everything. One `npm i -g` brings bob plus the orchestration stack it shells out
  to (`spawn.py`), the native coordination binaries (`herdr`, `orbal-net`), the eve L1 app,
  and an auto-installed microsandbox runtime - not "assume the herd is already installed".
- Design/RFC only.

This RFC packages what already exists. It does not re-architect the 3-layer model, the
orbal-net protocol, spawn.py's behavior, the shared-server model, or the confirm-gate - it
takes each as a given and asks only "how does it ship, install, and configure as one CLI".

Two positions are load-bearing and are fixed here before the rest follows:

1. The eve L1 app ships as a PREBUILT `.output` in the tarball (section 4), with
   `eve@0.22.1` pinned as an exact bundled dependency. Build-on-postinstall is rejected.
2. `.botfiles/orchestration` remains the HOME of `spawn.py`; the bob package VENDORS a
   pinned, provenance-stamped snapshot, with a `bob doctor` drift-check and the existing
   `ORCHESTRATION_DIR` override as the live-development escape hatch (section 6). Making bob
   spawn.py's home is rejected.

v1 platform scope is darwin-arm64 only (section 5.3): it is the only proven target, and
spawn.py's per-mission sandbox is Apple `container`, which is macOS-only. Linux is a named
follow-up, not v1.

## 2. Background: the current dev-repo UX this replaces

Grounded in `bin/bob`, `docs/HOST-RUN-PLAYBOOK.md`, `package.json`, `agent/sandbox.ts`,
`agent/lib/host-exec.ts`, and `orchestration/spawn.py`.

### 2.1 What launching bob costs today

`bin/bob` is a bash launcher with five verbs plus a default:

- `bob` (default) - `up` then attach the TUI.
- `bob up` - start the shared `orbal-net serve` (default `:4100`, persisted token + db),
  then eve (`:3000`, RESUME durable sessions), then the L1 connector (control `:3900`), all
  in the background.
- `bob tui` - attach the durable terminal client to the `bob:<host>` session.
- `bob status` - shared-server / eve / connector up-or-down.
- `bob down` - stop THIS bob process (eve + connector); leaves the shared server and any
  live mission running.
- `bob server-down` - stop the shared orbal-net server (every mission loses coordination).

Before any of that works, the operator must, by hand (playbook section 0): `npm ci`,
`vercel link` (writes `.env.local` with `VERCEL_OIDC_TOKEN`), run `npx eve dev` ONCE to
install the microsandbox libkrun runtime to `~/.microsandbox` (autoInstall fires only under
`eve dev`, never under `eve start`), `npx eve build`, then export `BOB_HOST_IDENTITY`,
`ORCHESTRATION_DIR` (so `host-exec.ts` resolves `spawn.py`/`plan_pane.py`), `HERDR_ENV=1`,
and optionally `ORBAL_NET_PORT`. `herdr`, `orbal-net`, `git`, `gh`, and Node >=24 must
already be on PATH. Every one of these manual steps is a target for `bob init`/`bob doctor`.

### 2.2 The two runtimes that are the hard part of "bundle everything"

There are two distinct sandbox runtimes, and conflating them is a trap:

- microsandbox / libkrun (`agent/sandbox.ts`) - eve's OWN sandbox for in-turn tool
  execution, installed to `~/.microsandbox`. `agent/sandbox.ts` pins `microsandbox({ setup:
  { autoInstall: true } })`, but autoInstall only self-heals under `eve dev`; `eve start`
  (what `bob` runs in production) fails at sandbox prewarm on macOS if the runtime is
  absent. This is the "run `npx eve dev` once" gotcha.
- Apple `container` (`spawn.py`) - the PER-MISSION microVM that spawned agents run inside.
  `spawn.py` shells out to the `container` CLI (`CONTAINER_IMAGE = "botfiles-agent"`, 8 CPU
  / 12g default). Apple `container` is macOS-only, which is the hard floor on v1 platform
  scope.

JS/TS plus a prebuilt `.output` are easy to put in an npm tarball. The native binaries
(`herdr`, `orbal-net`) and these two VM runtimes are the genuinely hard part; this RFC is
concrete about the mechanism for each rather than hand-waving "bundle it".

### 2.3 The credential pain

`bin/bob`'s `need_env` fails if `.env.local` is missing and tells the operator to run
`vercel link --yes --scope zico-ios-projects --project bob`, which writes a fresh
`VERCEL_OIDC_TOKEN`. The OIDC token is short-lived (~1 hour), so today the operator re-runs
`vercel link` about hourly. Killing that re-link is the sharpest single UX win (section 7).

## 3. Package layout (the north-star shape)

<!-- [worker-packaging] fills 3.x from the npm-layout research; rfc-lead integrates.
Target shape: the @zico/bob main package (bin/bob wrapper -> node entry, agent/ + connector/
+ client/ source, the PREBUILT .output, the vendored spawn.py/plan_pane.py snapshot, the
bundled eve@0.22.1 + runtime deps), plus the darwin-arm64 platform package carrying herdr +
orbal-net. Show the tree, the package.json bin/files/os/cpu/optionalDependencies fields, and
where each bundled artifact lands on disk after `npm i -g`. -->

## 4. The eve-app bundle: PREBUILT .output (decided)

Position: the npm package ships a PREBUILT `.output` produced at release/CI time against
`eve@0.22.1`, alongside the `agent/` + `connector/` + `client/` source. It does NOT build on
postinstall.

<!-- [worker-packaging] fills the tradeoff table + the mechanics: why prebuilt (no eve
toolchain at install, deterministic proven .output, fast npm i; build-on-install needs full
devDeps + a slow `eve build` on the user host + eve is beta and its build can churn); what
MUST still ship as source (connector/client run via `node --experimental-strip-types`; `eve
start` serves .output but needs the project); how eve@0.22.1 travels (exact dep + committed
lockfile, bundled node_modules); the `bob doctor --rebuild` local-rebuild escape hatch; and
the beta/churn caveat that a prebuilt .output couples the tarball to the eve build target. -->

## 5. Bundling the native orchestration binaries (herdr, orbal-net)

<!-- [worker-packaging] fills 5.1-5.2 from the native-binary distribution research.
Position to defend: per-platform optionalDependencies (the esbuild/@napi-rs pattern) - a thin
main package that declares an optionalDependency on @zico/bob-darwin-arm64, whose package.json
os/cpu fields make npm install ONLY the matching platform package; the herdr + orbal-net
binaries are vendored inside that platform package and marked executable. Compare against
postinstall-download-of-a-pinned-release (checksum/trust + offline-install failure modes) and
vendored-in-the-main-tarball (bloats every install with the wrong arch). Cover: how the binary
is resolved + exec'd at runtime, version pinning in lockstep with the main package, and the
offline-install story. -->

### 5.3 Platform coverage

Position: v1 is darwin-arm64 ONLY. It is the sole proven target, and spawn.py's per-mission
sandbox is Apple `container` (macOS-only), so the mission-spawning half cannot run on linux
without a different sandbox backend regardless of how the binaries ship. `bob doctor` fails
fast with a clear platform message on any other host. Linux (glibc + KVM, which microsandbox
itself supports) is a named follow-up, gated on a linux mission-sandbox backend - out of v1.

## 6. spawn.py source-of-truth and ownership (the crux of "bundle everything")

Position: `.botfiles/orchestration` REMAINS the home and source of truth for `spawn.py`
(and `plan_pane.py` and the orchestration glue). The `@zico/bob` package VENDORS a pinned,
provenance-stamped snapshot of them. Making bob spawn.py's home - moving spawn.py into the
bob repo and having `.botfiles` consume it - is rejected.

Why not bob-as-home. `spawn.py` (1286 lines) predates bob's packaging and has TWO consumers,
not one: bob (via `agent/lib/host-exec.ts`, which shells out to `${ORCHESTRATION_DIR}/spawn.py`)
AND the legacy claude-L1 orchestrator - a raw claude pane that runs `spawn.py` directly, plus
the `.claude/commands/spawn-team.md` command that `.botfiles` ships. `host-exec.ts` states the
current contract outright: "spawn.py and plan_pane.py live in host .botfiles/orchestration, not
in this repo (non-goal: do not copy/modify them here)". spawn.py is actively developed in
`.botfiles`. Moving it into the bob repo would invert a mature, actively-developed orchestration
stack under a newer packaging shim and force `.botfiles` to take a build/runtime dependency on
bob. That is the wrong ownership direction.

The drift risk, named. Vendoring a copy risks two diverging `spawn.py`s: a fix landed in
`.botfiles` is not in a `bob` user's hands until the next bob release re-vendors it, so a
`bob`-shipped copy can lag the copy the claude-L1 pane runs. This is the real cost of
vendor-with-sync and this RFC does not pretend it away.

The ownership model + drift controls:

- Canonical, one direction. `.botfiles/orchestration/spawn.py` is canonical. The bob package's
  copy is a downstream snapshot, refreshed by a scripted `vendor-sync` at bob release time
  (copy from a pinned `.botfiles` ref), never hand-edited - consistent with the repo rule
  "never hand-edit auto-generated files".
- Provenance stamp. The vendored copy carries the source `.botfiles` commit SHA (a provenance
  header / `SPAWN_PY_VERSION`), so any host can report exactly which spawn.py it is running.
- `bob doctor` drift-check. `bob doctor` reports the vendored spawn.py's provenance SHA and
  warns if it lags the pin the release expects; the version story (section 8) keeps it moving
  in lockstep with the rest of the bundle.
- Live-dev escape hatch. The existing `ORCHESTRATION_DIR` override (honored by `host-exec.ts`)
  lets a bob developer point bob at a live `.botfiles` checkout, so anyone actually developing
  spawn.py runs the canonical copy, never the vendored snapshot. The vendored copy is the
  default for a plain `npm i -g` host that has no `.botfiles` clone at all - which is exactly
  what "bundle-everything" must deliver.

Net: HOME stays `.botfiles`; bob carries a pinned, stamped, drift-checked snapshot with an
override for live development. This makes a fresh host self-contained without inverting a
mature stack, and is honest about the lag it introduces.

## 7. Config, credentials, and the CLI command surface

### 7.1 Config file: `~/.config/bob/config.toml`

`bob init` writes `~/.config/bob/config.toml`, and it replaces every one of today's hand-exported
env vars (2.1): `BOB_HOST_IDENTITY`, `ORCHESTRATION_DIR`, `HERDR_ENV`, `ORBAL_NET_PORT`. Schema:

```toml
[bob]
host_identity = "corvid"          # was BOB_HOST_IDENTITY; default = hostname() at init time
orchestration_dir = ""            # was ORCHESTRATION_DIR; "" (default) resolves at RUNTIME to the
                                   # PACKAGE'S OWN vendored orchestration/ (S6) - never a hardcoded
                                   # absolute path, since npm's global prefix varies (nvm/volta/system)
orbal_net_port = 4100             # was ORBAL_NET_PORT
state_dir = "~/.local/state/bob"  # NEW: home for .workflow-data, the orbal-net db/token, and logs -
                                   # see 9.2; no env-var predecessor today because bin-bob.sh writes
                                   # these repo-root-relative, which a packaged bob cannot do

[auth]
ai_gateway_api_key = ""           # written by `bob login` (7.2); replaces VERCEL_OIDC_TOKEN + .env.local
ai_gateway_key_id  = ""           # the key's Vercel-side id, so `bob login --rotate`/doctor can revoke it
vercel_scope   = "zico-ios-projects"
vercel_project = "bob"
```

`HERDR_ENV` gets no config field at all: it becomes implicit, since herdr ships bundled and on PATH
via the platform package (S5) and bob's own tooling can check for herdr's presence directly instead
of gating on an operator-set flag.

Precedence, highest first: **live environment variable > config.toml > built-in default.** This is
the standard CLI-config pattern and matters for two concrete cases: (1) `AI_GATEWAY_API_KEY` or
`VERCEL_OIDC_TOKEN` already exported (CI, a secrets manager) is used as-is and `bob login`/config's
`auth.*` fields are never consulted; (2) a migrating dev-repo operator's existing shell exports
(`BOB_HOST_IDENTITY` etc., 9.2) keep working unchanged the moment they install the package, so
migration cannot silently break a running setup - `bob doctor` nudges toward removing the exports
once config.toml covers them, but never requires it.

The locked default matters concretely: `orchestration_dir`'s default is the vendored spawn.py
*inside the global package* (S6), so a plain `npm i -g @zico/bob` host needs no `.botfiles` clone
at all to run missions - that is what "bundle-everything" buys over today's
`ORCHESTRATION_DIR=<path to a .botfiles clone you must already have>`.

### 7.2 Vercel auth: killing the hourly re-link

Today's pain (2.3): `vercel link` writes `.env.local` with a `VERCEL_OIDC_TOKEN` that expires and
needs an operator to re-run `vercel link` roughly hourly, since bob is not itself a Vercel
deployment - it is a long-running local process pulling a project-linked token, not the
always-fresh token a deployed app gets for free.

Grounded position: bob does not refresh OIDC - it **replaces OIDC with a long-lived AI Gateway API
key**, and never touches `vercel link` or `.env.local` again. This is possible because the AI
Gateway supports two independent auth methods, and the AI SDK (bob's direct dependency,
`ai: ^7.0.0`) natively prefers the key over the token:

- OIDC tokens are short-lived by design - Vercel's own docs state they are valid 12h in local dev
  (refreshed by re-running `vercel env pull`) and shorter in production/preview, and require a
  linked project ([Vercel: OIDC](https://vercel.com/docs/ai-gateway/authentication-and-byok/oidc) -
  proves the token's lifetime and that `vercel link` + `vercel env pull` is the only refresh path).
- API keys **never expire unless revoked**, work anywhere (local dev, servers, CI) with no linked
  project required, and the AI SDK's gateway provider auto-resolves them ahead of OIDC - the docs
  show the exact fallback bob's dependency already implements:
  `process.env.AI_GATEWAY_API_KEY || process.env.VERCEL_OIDC_TOKEN`
  ([Vercel: Authentication & BYOK](https://vercel.com/docs/ai-gateway/authentication-and-byok) -
  proves API keys are non-expiring and are the SDK's preferred credential over OIDC).
- Keys are created non-interactively via `vercel ai-gateway api-keys create --name <name>` (or the
  REST `POST /v1/api-keys`), returning the raw secret exactly once and a stable `id` used later to
  list/revoke it; an optional `expiresAt` and spend budget can be set at creation
  ([Vercel: API Keys](https://vercel.com/docs/ai-gateway/authentication-and-byok/api-keys) - proves
  the CLI/REST creation call, one-time secret reveal, and the `id`-based revoke flow bob's
  `login --rotate` needs).

Design: `bob login` runs `vercel login` if the operator isn't already authenticated, then
`vercel ai-gateway api-keys create --name bob-<host_identity>` under `zico-ios-projects`, and
writes the returned secret + id straight into `config.toml`'s `[auth]` (7.1) - this is the only
capture point, since Vercel never shows the raw key again. `bob up` exports `AI_GATEWAY_API_KEY`
(not `VERCEL_OIDC_TOKEN`) into eve's process env before `eve start`; bin-bob.sh's `need_env` gate
(".env.local missing -> run vercel link") is replaced by "config.auth.ai_gateway_api_key missing ->
run bob login". No fallback re-auth prompt is needed here - unlike a "least-bad" workaround, this
is a clean substitution the AI SDK already supports.

Two risks worth naming rather than hiding (also 11.1, S10 #2): the docs state a key is deactivated
if the Vercel team member who created it leaves the team - a bob key tied to one person's login is
a standing organizational risk unless minted under a team/bot Vercel identity (open question, S10);
and while API keys are documented as stable today (doc revision 2026-06-20), they are still part of
a beta product surface (AI Gateway) whose env-var precedence Vercel could change in a future `ai`
SDK major - `bob doctor`'s key-liveness probe (7.3) is the containment, since it turns any future
auth break into a clear diagnosed failure instead of a silent eve boot failure.

### 7.3 CLI command surface

- **`bob`** (default) - unchanged from today (2.1): `up`, then attach the TUI.
- **`bob init`** - first-run setup. CHECKS and AUTO-FIXES, in order:
  - Node >=24 and git on PATH - CHECK only (host toolchain, not bob's to install; fails with a
    clear message pointing at the host's own package manager).
  - `herdr`/`orbal-net` binaries present and executable - CHECK (should already be true post-
    `npm i -g` via the platform optionalDependency, S5); AUTO-FIXES a lost exec bit.
  - `gh` on PATH and authenticated - CHECK only (needed for `spawn_bridge_pr`; points at
    `gh auth login`).
  - `~/.config/bob/config.toml` missing - AUTO-FIXES by writing the default (7.1).
  - `auth.ai_gateway_api_key` missing - AUTO-FIXES by running the `bob login` flow (7.2).
  - `~/.microsandbox` runtime missing - AUTO-FIXES by running the install mechanism (7.4).
  - vendored spawn.py provenance (S6) - reports the pinned SHA informationally; no fix (drift
    detection is `doctor`'s job, S8).

  init is idempotent: every check that already passes is a no-op, so re-running it after a partial
  failure is always safe.
- **`bob login`** - standalone re-auth entry point; the same key-mint flow as init's auth step,
  callable any time. `bob login --rotate` mints a fresh key and revokes the old one (via the
  `id`-based delete call, 7.2) rather than leaving both live.
- **`bob doctor`** - the repair path, safe to run any time bob misbehaves. Re-runs init's full
  check list LIVE (not "was this ever set up") and is explicit about drift rather than silent about
  it: native-binary version vs the main package's pin (S8) - report, fix suggests `npm i -g
  @zico/bob` reinstall; eve pin vs `0.22.1` - report only; vendored spawn.py SHA vs the release's
  expected pin (S6) - report only; microsandbox runtime - re-probes and AUTO-FIXES by re-running
  the install mechanism (this is doctor's direct answer to "`eve start` does not self-heal it",
  2.2); config schema - AUTO-FIXES missing optional keys, refuses to guess required ones; AI
  Gateway key liveness - AUTO-FIXES a revoked key by re-running login; platform (5.3) - CHECK only,
  hard-fails clearly off darwin-arm64. doctor and init share one check surface; they differ only in
  framing (repair vs first-run) and in doctor treating "already set up" as something to re-verify,
  not assume.
- **`bob up` / `bob tui` / `bob status` / `bob down` / `bob server-down`** - identical verbs and
  semantics to `bin/bob` today (2.1); packaging changes only the entry point (global `bob` instead
  of a repo-relative script) and removes what `up` no longer needs to do - no `npm ci`, no `npx eve
  build`, no `.env.local`/`vercel link` gate, all absorbed into `init`/`doctor` and the prebuilt
  `.output` (S4).
- **`bob version`** - prints the S8 coherence report (bob JS version, platform-package version, eve
  pin, spawn.py provenance SHA) as a static read, no live checks.
- **`bob update`** - shells to `npm i -g @zico/bob@latest`, then runs `bob doctor` automatically,
  so a version bump always lands in a verified-coherent state instead of leaving the operator to
  remember the doctor step (S8).

### 7.4 The microsandbox install step (mechanism co-owned with S5.2)

`bob init` and `bob doctor` both run the microsandbox runtime bootstrap as one blocking step
(spinner shown - first install fetches a VM image and can take tens of seconds) before continuing
to the next check. `agent/sandbox.ts` already pins `autoInstall: true`, but that only self-heals
under `eve dev`, never under the `eve start` bob actually runs (2.2) - so bob's own init/doctor is
the thing that has to trigger the install, not eve.

Which exact handle it calls is S5.2's mechanism to defend, but the research for this section
surfaced a concrete alternative to the documented `eve dev`-boot-and-kill trick worth flagging to
worker-packaging: the microsandbox project ships its own official, non-interactive installer
independent of eve, and its own npm package documents auto-installing the native `msb` binary and
`libkrunfw` on first run ([microsandbox on GitHub](https://github.com/superradcompany/microsandbox)
- proves `curl -fsSL https://install.microsandbox.dev | sh` is the official installer and that SDK
packages download the runtime to `~/.microsandbox/` on first use, independent of `eve dev`). If
that holds up, `bob init`/`doctor` can invoke the microsandbox package's own install path (or shell
the official installer) directly, instead of scripting a throwaway `eve dev` boot-wait-kill - a
materially simpler, more legible failure mode for this step.

The UX contract is fixed regardless of which mechanism S5.2 lands on: on an unsupported host (5.3 -
not darwin-arm64) this step fails FAST with the platform message before attempting any network
install; on a supported host, a failure here is expected to be the single most common first-run
failure (it is the one step needing real network I/O to fetch a VM image), so init/doctor print the
exact remediation (`bob init` again, or the manual installer command as a fallback) rather than a
bare stack trace.

## 8. Update and version story

<!-- [worker-packaging] fills. Position: ONE version number for the main package + its platform
package(s), moved in lockstep (esbuild-style), so `npm update -g @zico/bob` never desyncs the
native binaries from the JS. The eve@0.22.1 pin is bumped only deliberately (eve is beta). The
vendored spawn.py snapshot is refreshed per release and carries its provenance SHA (section 6).
`bob doctor` verifies all four (bob JS, native binaries, eve pin, spawn.py snapshot) are
coherent after an update. Name what breaks if any one drifts. -->

## 9. First-run flow and migration off the dev-repo

### 9.1 Fresh host: the new sequence

Mapping every manual step in today's playbook section 0 (2.1) onto a command:

| Today (HOST-RUN-PLAYBOOK.md step 0) | Becomes |
|---|---|
| `git clone zico-io/bob && cd bob && npm ci` | `npm i -g @zico/bob` |
| `vercel link --yes --scope zico-ios-projects --project bob` (writes `.env.local`) | `bob init` (auto-runs `bob login`, 7.2/7.3) |
| `npx eve dev` once, Ctrl-C, to install `~/.microsandbox` | `bob init`'s microsandbox check/auto-fix (7.4) |
| `npx eve build` | nothing - the `.output` ships prebuilt (S4) |
| hand-export `BOB_HOST_IDENTITY`/`ORCHESTRATION_DIR`/`HERDR_ENV`/`ORBAL_NET_PORT` | `bob init` writes `~/.config/bob/config.toml` (7.1) |
| `bin/bob` | `bob` |

So the fresh-host sequence collapses to three commands:

```
npm i -g @zico/bob
bob init      # config + AI Gateway key + microsandbox runtime + preflight checks, all idempotent
bob           # up + attach TUI - durable, all-day, no repo checkout on this host at all
```

Two host prerequisites this RFC does not remove (S10 #5): Node >=24 and `gh` (authenticated) must
already be on PATH - `bob init`/`doctor` CHECK both but do not install either, consistent with how
npm-global CLIs generally treat the host's own toolchain rather than trying to manage it.

### 9.2 Migration for the current dev-repo operator

Every artifact of today's setup maps onto something in the packaged world:

- **The `zico-io/bob` clone** - no longer required to *run* bob. Still required to *develop* bob
  (this RFC changes distribution, not the dev loop) - `bin/bob` stays the contributor-facing entry
  point inside the clone; a separate operator no longer needs the clone at all.
- **Hand-exported env vars** - become `config.toml` fields (7.1). Because env still overrides
  config, an operator's existing shell exports keep working unchanged on day one of migration;
  `bob doctor` nudges toward retiring them, never forces it.
- **`.env.local` / hourly `vercel link`** - replaced by `bob login`, run once (7.2). The old
  clone's `.env.local` becomes dead weight bob no longer reads (bob does not run from that clone
  post-migration).
- **`~/.microsandbox`** - already installed for an existing dev-repo operator from their prior
  `npx eve dev` runs. `bob init`'s check (7.4) detects it and no-ops - migration does not redo
  this step.
- **`bin/bob`** - becomes the packaged `bob` global command; the repo-local script is retained only
  as the contributor dev-loop entry point for bob's own repo (out of this RFC's scope to remove),
  not as something an operator runs anymore.
- **`docs/HOST-RUN-PLAYBOOK.md`** - its step 0 (setup) is fully replaced by 9.1 and by `bob
  doctor`'s live output; the still-relevant human-in-the-loop material - the scope-mission/
  spawn-team walkthrough and the confirm-gate two-turn flow (HOST-RUN-PLAYBOOK.md steps 2-4) - is
  about *using* bob, not installing it, and survives as the packaged product's own usage docs.
- **Durable state** - the sharpest migration risk, not covered by any locked section above.
  `bin/bob` writes `.workflow-data` (eve's durable session), `.bob-orbal-net.db`/
  `.bob-orbal-net.token` (the shared server), and logs *repo-root-relative*
  (bin-bob.sh: `cd "$(dirname "$0")/.."`, 2.1) - a packaged `bob` has no repo root to be relative
  to. This RFC's config adds a `state_dir` field (default `~/.local/state/bob`, 7.1) as that stable
  home, and migration is not just "start using the new commands" - it requires **moving**
  `.workflow-data` and the orbal-net db/token from the old clone into the new `state_dir` by hand
  (or via a `bob init --migrate-from <old-clone-path>` convenience flag), or the operator loses
  their all-day durable session and mission history on migration day. Flagged as its own top risk
  in S10, not a footnote, because it is easy to design past silently.

## 10. Ranked open questions and the recommended first increment

Most load-bearing first - each blocks or materially changes something already locked above, not a
general wishlist:

1. **The durable state directory is undefined in the current design.** `bin/bob` writes
   `.workflow-data`, the orbal-net db/token, and logs relative to the repo root (2.1, 9.2); a
   packaged `bob` has no repo root. This RFC proposes `state_dir` in `config.toml` (default
   `~/.local/state/bob`, 7.1), but it needs to be locked before implementation - and it must
   survive `npm update -g`, which can touch the package's own install tree. Highest-load-bearing
   because getting it wrong loses the all-day durable session - the RFC's headline feature - on
   the very first update or migration.
2. **The AI Gateway API key (7.2) is tied to the Vercel account that created it.** Vercel's own
   docs warn a key is deactivated when its creating team member leaves the team - a `bob login`
   key minted under one operator's personal login is a standing organizational risk, not a
   one-time setup detail. Needs investigating whether `zico-ios-projects` has (or should have) a
   team/bot Vercel identity to mint bob's key under, before `bob login` ships as designed.
3. **The microsandbox install mechanism (7.4/5.2) is not yet confirmed**, only researched -
   whether bob invokes the microsandbox npm package's own auto-install, its official installer
   script, or the current `eve dev`-throwaway-boot trick changes the S3 dependency graph and the
   exact S7.4 failure mode. Must land before `init`/`doctor` can be built, not just designed.
4. **spawn.py drift (S6) is invisible unless `bob doctor` is run habitually.** The vendored copy
   is the default for every `npm i -g` host, and the only drift signal is `doctor`'s
   provenance-SHA check - a host that never runs `doctor` never learns it has fallen behind
   `.botfiles`. Consider surfacing the provenance SHA in `bob status` too (2.1's most-run
   command), not only `doctor`/`version`.
5. **`gh` auth and Node >=24 stay unmanaged host prerequisites** (9.1) - `init`/`doctor` check but
   never install either. Consistent with how npm-global CLIs usually treat host toolchain, but
   should be stated as a deliberate non-goal so "bundle-everything" doesn't get read as "bundles
   the host's own package managers too."
6. **`bob login` (7.2) itself needs a Vercel CLI or REST dependency decision.** Minting a key via
   `vercel ai-gateway api-keys create` needs the Vercel CLI on the host (another native dependency
   to pin, akin to S5's herdr/orbal-net) or a hand-rolled call against the REST
   `POST /v1/api-keys` endpoint using a Vercel personal access token (fewer moving parts, but a
   worse first-run UX - the operator needs to mint that token first). Leans REST but is a real
   design decision, not just a citation, and isn't made here.
7. **Should `bob init` set a spend budget on the AI Gateway key it mints by default?** An
   unattended, all-day orchestrator holding an unbounded non-expiring key is a real cost-runaway
   risk (7.2). A conservative default budget with a `bob init --budget <amount>` override is
   proposed but is a product call (what "conservative" means for this team), not an engineering
   one.

<!-- rfc-lead: recommended first build increment to follow here, reconciled against S4-S8. -->

## 11. Appendix

### 11.1 Beta-churn risk register

<!-- Both workers feed this: eve is a Vercel beta (build output shape, sandbox API, start
semantics can churn); Vercel AI Gateway auth model may change; Apple `container` is young.
Each row: the dependency, the churn it can throw, and bob's containment. -->

### 11.2 Sources

<!-- Both workers append cited current docs (eve, npm optionalDependencies/os-cpu, Vercel AI
Gateway auth, microsandbox). Every eve/npm/Vercel-auth claim in the body cites a row here. -->
