# RFC: bob-cli - packaging bob into a self-contained, installable npm-global orchestrator

- Status: Draft (packaging/distribution RFC; no shipped code)
- Owner: rfc-lead (mission bob-cli)
- Date: 2026-07-10
- Scope: design and prose only. This RFC does not modify `bin/bob`, `spawn.py`, the eve app, or orbal-net; it consumes the merged bob, the 3-layer model, the shared-server model, and the confirm-gate as proven givens and takes a concrete position on how bob ships, installs, and configures as one npm-global CLI. It is local-first: a remote/Vercel-deployed orchestrator and a compiled standalone binary are named as possible futures, not designed here.

---

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

Two packages ship as one release, versioned in lockstep (section 8): the main package `@zico/bob`
(JS/TS source + the prebuilt eve output + a vendored orchestration-scripts snapshot) and one
platform package per supported host, `@zico/bob-darwin-arm64` (v1: this is the only one - section
5.3), carrying the two native binaries.

Tree of `@zico/bob` as it lands under npm's global `node_modules` after `npm i -g @zico/bob`:

```
{npm root -g}/node_modules/@zico/bob/
├── package.json
├── bin/
│   └── bob                      # node shebang entry; replaces bin/bob's (bin-bob.sh) role 1:1 -
│                                 #   same up/tui/status/down/server-down state machine, ported to
│                                 #   node so it resolves package-relative paths (agent/, .output/,
│                                 #   vendor/, the platform package) instead of
│                                 #   `cd "$(dirname "$0")/.."`
├── agent/                       # the eve project source - ships unchanged from the repo
│   ├── sandbox.ts
│   ├── lib/
│   │   ├── confirm-gate.ts
│   │   └── host-exec.ts         # orchestrationDir() default becomes vendor/ (section 6 and 7.1),
│   │                             #   not /opt/botfiles/orchestration
│   └── tools/
│       ├── spawn_up.ts  spawn_down.ts  spawn_poke.ts  spawn_status.ts  spawn_bridge_pr.ts
│       ├── herdr_pane_read.ts
│       └── plan_pane_open.ts  plan_pane_selection.ts  plan_pane_close.ts
├── connector/
│   └── main.ts                  # run via `node --experimental-strip-types`, not eve-compiled
├── client/
│   └── bob-tui.ts                # ditto - the BOB_TUI_ENTRY default
├── .output/                     # PREBUILT eve/Nitro build output (section 4) - built at
│   └── server/index.mjs         #   release/CI time, shipped verbatim, never rebuilt on install
├── vendor/
│   ├── spawn.py
│   ├── plan_pane.py
│   └── PROVENANCE                # the source .botfiles commit SHA this snapshot was cut from
│                                  #   (section 6 / section 8)
└── node_modules/                 # BUNDLED (bundledDependencies, 4.3) - eve@0.22.1's full
    └── ...                       #   resolved tree, shipped inside the tarball itself
```

npm creates the global bin symlink itself from the `bin` field, identically on every OS:
`{npm prefix}/bin/bob -> {npm root -g}/node_modules/@zico/bob/bin/bob`, executable bit set
automatically.

Platform package:

```
{npm root -g}/node_modules/@zico/bob-darwin-arm64/
├── package.json                  # os:["darwin"], cpu:["arm64"], NO "bin" field - see 5.2.1
└── bin/
    ├── herdr                     # vendored native binary, chmod +x at publish time
    └── orbal-net                 # vendored native binary, chmod +x at publish time
```

`package.json` fields, `@zico/bob`:

```jsonc
{
  "name": "@zico/bob",
  "version": "1.0.0",                    // moves in lockstep with the platform package (section 8)
  "bin": { "bob": "bin/bob" },
  "files": ["bin", "agent", "connector", "client", ".output", "vendor", "package.json"],
  "os": ["darwin"],                      // v1 is darwin-arm64 END TO END (5.3) - the whole
  "cpu": ["arm64"],                      //   product, not just the native binaries - so
                                          //   `npm i -g` fails fast with npm's own EBADPLATFORM
                                          //   on any other host instead of installing a CLI
                                          //   that can never work
  "optionalDependencies": {
    "@zico/bob-darwin-arm64": "1.0.0"    // exact match to the main package's own version
  },
  "dependencies": {
    "eve": "0.22.1",                     // exact, not ^ - beta, pinned deliberately (section 8)
    "ai": "^7.0.0",
    "@vercel/connect": "0.2.2",
    "zod": "4.4.3"
  },
  "bundledDependencies": ["eve", "ai", "@vercel/connect", "zod"],   // section 4.3
  "engines": { "node": ">=24" }
}
```

Deliberate deviation from the esbuild pattern (5.1), named explicitly: esbuild's main package
carries NO `os`/`cpu` restriction - it installs everywhere and lets the per-platform
`optionalDependency` silently fail to match on an unsupported host [source 4]. `@zico/bob`
restricts the MAIN package too, because bob is not "a binary with a thin JS wrapper" the way
esbuild is - its non-native half (Apple `container` mission sandboxing, microsandbox's
macOS-only-in-v1 libkrun path) is exactly as platform-locked as its native binaries (5.3). `bob
doctor` (7.3) still exists for a borderline host that gets past npm's gate (e.g. Rosetta), but
npm's own platform check is the first, cheapest line of defense - free, and fires before a single
byte of the package downloads.

End state: `npm i -g @zico/bob` places exactly two package directories under npm's global
`node_modules`, one `bob` symlink on PATH, and every artifact bob needs already on disk - no
postinstall network fetch beyond npm's own package resolution (everything else is bundled or
`bundledDependencies`), no separate `cargo install`, no separate download for `herdr`/`orbal-net`.
Note what is deliberately NOT in this tree: no `.workflow-data`, no orbal-net db/token, no logs.
All mutable runtime state lives OUTSIDE the package under `state_dir` (7.1, default
`~/.local/state/bob`), because `npm update -g` replaces this whole directory (section 8) - keeping
state here would destroy the durable session on every update.

## 4. The eve-app bundle: PREBUILT .output (decided)

Position: the npm package ships a PREBUILT `.output` produced at release/CI time against
`eve@0.22.1`, alongside the `agent/` + `connector/` + `client/` source. It does NOT build on
postinstall.

### 4.1 Tradeoff: prebuilt vs. build-on-install

| | Prebuilt `.output` (chosen) | Build-on-install |
|---|---|---|
| Toolchain needed at `npm i -g` time | none - `.output` is a plain Nitro server bundle [source 11], started by `eve start`/node | the full `devDependencies` tree (`typescript@7.0.1-rc`, `microsandbox@^0.5.10`, `just-bash@^3.0.0`) plus `eve build` itself, run on the end user's host |
| Install time | fast - unpack + link, no compile step | slow - `eve build` compiles agent/ discovery + Nitro bundling on every fresh global install, on hardware bob's release process never tested |
| Determinism | the exact `.output` that passed CI/release testing ships bit-for-bit to every install | the user's local `eve build` output depends on whatever `eve` resolves at their install moment - `eve` moved `0.22.1` -> `0.22.4` [source 1] in the time this RFC was being drafted, so an unpinned build-on-install can silently pick up a build-output shape nobody on bob's side tested |
| Failure surface | contained to bob's release pipeline - one build, one test pass, shipped frozen | distributed to every user's machine - a broken `eve build` on someone's laptop is now a bob support ticket, not a CI failure |
| Offline install | works - no build-time network calls beyond npm's own resolution | `eve build`'s discovery/compile step and any devDep install can need network |

### 4.2 What still ships as source

`.output/` alone is not the shipped unit - `eve start` is invoked from, and serves relative to,
the project directory ("`eve start` serves `.output` but needs the project"), so `agent/` (the eve
project itself: `sandbox.ts`, `lib/`, `tools/`) ships as real TypeScript source next to `.output/`,
unchanged from the repo, read by `eve start` at boot even though it is never recompiled there.
`connector/main.ts` and `client/bob-tui.ts` are NOT eve-compiled at all - they are the plain Node
entry points `bin/bob` already runs today via `node --experimental-strip-types connector/main.ts` /
`client/bob-tui.ts` (`bin-bob.sh`:177,187), so they ship as `.ts` source and run identically
post-packaging. Nothing here is stripped down for the package: the same three source trees
(`agent/`, `connector/`, `client/`) that exist in the repo today ship byte-for-byte inside
`@zico/bob`; `.output/` is the one genuinely NEW artifact, generated once at release time, not per
install.

### 4.3 How eve@0.22.1 travels

`eve` stays an ordinary `"dependencies"` entry, pinned EXACT (`"eve": "0.22.1"`, no `^`) - it is a
Vercel beta and churns across even patch versions (`0.22.4` is current tip as of this research,
against the `0.22.1` this RFC pins [source 1]). An exact pin in `dependencies` is not, by itself,
enough for a GLOBAL install to be fully deterministic: `npm i -g` resolves `@zico/bob`'s dependency
tree fresh against the registry using ordinary semver resolution, and a published package's own
`package-lock.json` is explicitly NOT consulted when that package is installed as a dependency of
something else - npm's docs state it directly: "`package-lock.json` cannot be published, and it will
be ignored if found in any place other than the root project" [source 2]. So `eve@0.22.1`'s own
transitive tree can drift release to release even with bob's own pin held constant.

Position: mark `eve` (and its co-pinned direct deps `ai`, `@vercel/connect`, `zod`)
`bundledDependencies` [source 3] in `@zico/bob`'s `package.json`. `npm pack`/`npm publish` then
embeds a real, fully-resolved `node_modules/` snapshot inside the published tarball itself; on
`npm i -g`, npm extracts that snapshot as-is instead of re-resolving from the registry [source 3].
This is the strongest determinism npm offers: the exact `eve@0.22.1` plus the exact transitive tree
bob's release CI built `.output` against is what every user gets, byte-for-byte - immune to `eve`
being unpublished/deprecated/patched out from under a later install, and installable fully offline.
The cost is tarball size (a full `node_modules/eve` plus its deps, plausibly tens of MB) -
acceptable under the decided bundle-everything thesis (section 1), and no larger in kind than what
`optionalDependencies` already commits to for the native platform package (section 5).

### 4.4 The `bob doctor --rebuild` escape hatch

Shipping `.output/` prebuilt does not remove the ability to rebuild locally. `bob doctor --rebuild`
runs `eve build` against the shipped `agent/` source in place (using the bundled `eve` from
`node_modules/` - no extra install), overwriting that package's own `.output/` inside the global
install directory. This exists for two cases only: (a) a host where the prebuilt `.output` fails to
boot for a reason CI didn't catch (a Node minor-version quirk, a corrupted global install), and (b)
a bob developer pointed at a live source checkout via an `ORCHESTRATION_DIR`-style override, who
needs local edits reflected without cutting a release. It is explicitly NOT the default path -
section 4.1's entire argument is that build-on-install-by-default is the rejected option - so it is
gated behind an explicit flag; a plain `npm i -g` / `bob init` never triggers it silently.

### 4.5 Beta-churn caveat (feeds 11.1)

A prebuilt `.output` couples every bob release to the exact `eve` build-output shape at the moment
of that release. `bundledDependencies` (4.3) prevents the sharpest version of this risk (a user's
installed `eve` version only ever changes when a bob release changes it, so `.output` and its `eve`
are always the pair CI tested). The residual risk is narrower: `eve start`'s runtime *behavior* (not
the `.output` shape) changing between eve versions bob pins across releases - contained by the exact
pin at any single point in time, but still a beta dependency whose release cadence and
breaking-change discipline this RFC does not control.

## 5. Bundling the native orchestration binaries (herdr, orbal-net)

### 5.1 What "native binary" actually means here, today

The two are not symmetric in the grounding material. `orbal-net` is documented end to end: one Rust
binary, published at `github.com/zico-io/orbal-net`, distributed via `cargo install orbal-net`
(falling back to `cargo install --git ...` until a crates.io release lands). `spawn.py`'s own
`_ensure_orbal_net()` performs exactly this bootstrap today on the host
(`orchestration/spawn.py`:385-399), and the sandbox image's Containerfile does the guest-side
equivalent at build time. `herdr` has NO equivalent install path anywhere in this mission's
grounding set - it is assumed already on PATH (`HOST-RUN-PLAYBOOK.md` prerequisites, the
`HERDR_ENV=1` precondition) and never appears in `provision.sh` or the Containerfile.

This RFC's packaging mechanism (5.2) does not need to know herdr's build toolchain - it only needs
herdr as a compiled, `chmod +x`, per-platform executable to vendor, exactly like `orbal-net`.
Flagged explicitly rather than waved through: herdr's actual build/release process is UNVERIFIED
against source in this mission's grounding set, and either confirming it or getting per-platform
herdr binaries bob's release CI can pull is a real precondition of implementation (section 10 #2,
11.1), not a packaging detail this RFC can resolve from what it was given to read.

### 5.2 Distribution mechanism: per-platform optionalDependencies (the esbuild pattern)

Position: `@zico/bob` never runs `cargo install` or downloads anything at install time. It ships
`herdr` + `orbal-net` as prebuilt executables inside a separate, platform-scoped npm package
(`@zico/bob-darwin-arm64`, section 3), declared as an `optionalDependency` of the main package.
This is the same mechanism esbuild uses for its ~25 platform binaries [source 4]:
`@esbuild/darwin-arm64`'s `package.json` carries `"os": ["darwin"], "cpu": ["arm64"]` and no other
gating [source 5]; npm's installer reads those fields against `process.platform`/`process.arch`
[source 6, source 7] and silently skips installing any optional dependency whose `os`/`cpu` doesn't
match the current host - a skipped/failed optional dependency does not fail the parent install, that
is the entire point of `optionalDependencies` [source 6]. A `darwin-arm64` host installs
`@zico/bob-darwin-arm64` and nothing else; any other host (once a second platform package exists,
5.3) installs neither and moves on.

Compared to the two alternatives named in the brief:

- **postinstall-download of a pinned release** (a `postinstall` script that curls a GitHub release
  asset for the detected platform): adds a runtime network dependency to every single install (fails
  offline, fails behind a mirror/proxy that blocks arbitrary GitHub hosts), and moves integrity
  verification into hand-rolled script code (checksum it yourself, decide what "verified" means,
  handle partial/corrupt downloads) instead of npm's own tarball integrity (npm computes and the
  registry serves an integrity hash npm verifies automatically on every install - no extra code
  needed). This is, in effect, what `orbal-net`'s CURRENT distribution (`cargo install`) already is -
  a build/download at install time - and it is exactly the fragility (network dependency,
  `cargo`-on-PATH precondition, a "tried crates.io and git, install manually" failure message
  (`spawn.py`:385-399)) that bundle-everything (section 1) exists to eliminate.
- **vendored in the main tarball** (ship `herdr`+`orbal-net` binaries for every supported platform
  directly inside `@zico/bob`, no separate package): every install downloads every platform's binary
  regardless of host, bloating a darwin-arm64 user's install with binaries they can never run the
  moment a second platform ships. Harmless functionally, wasteful in bandwidth/disk, and is the
  anti-pattern esbuild's own platform-package split was created specifically to move away from
  [source 8].

v1 ships only `@zico/bob-darwin-arm64`, so the bandwidth argument is currently moot (there is only
one platform package to install), but the shape is chosen now, not deferred: it is the only one of
the three that survives adding a second platform (5.3's named Linux follow-up) without an npm
package restructure - add `@zico/bob-linux-x64` as a sibling package plus one more
`optionalDependencies` entry; `@zico/bob`'s own shipped files never change.

#### 5.2.1 Resolution and exec at runtime

`@zico/bob-darwin-arm64` carries no `"bin"` field of its own - a platform package is not
independently useful, only a payload the main package reaches into. `bin/bob` (the main package's
entry, section 3) resolves the two binaries the same way esbuild's JS wrapper resolves its native
binary: via `require.resolve`/`import.meta.resolve` against `@zico/bob-darwin-arm64`'s known package
name, not by assuming a bare `herdr`/`orbal-net` is already on PATH. `bin/bob` then either execs
them directly by absolute path (e.g. `orbal-net serve` at `bob up`) or PREPENDS that platform
package's `bin/` directory onto `PATH` for the process tree it spawns - so `spawn.py`'s own
`shutil.which("orbal-net")` check (`spawn.py`:392) and every `orbal-net <cmd>` a lead/worker types
keep working completely unmodified; no changes needed inside `spawn.py` or the harness bootstrap
prompts. The vendored binaries are marked executable (`chmod +x`) at PUBLISH time, as part of the
release pipeline that produces `@zico/bob-darwin-arm64`'s tarball, not on install - npm preserves the
executable bit through pack/publish/install for files under `bin/` [source 6], the same guarantee
esbuild's own binary packages rely on.

#### 5.2.2 Offline-install story

Because both binaries are inside a tarball npm already fetched (no separate download, no `cargo
install`, no postinstall network call), `npm i -g @zico/bob` is fully offline-capable from an
npm-compatible mirror/cache the moment both package tarballs are in it - the same offline story
`bundledDependencies` gives `eve` (4.3). This is the concrete improvement over `orbal-net`'s CURRENT
`cargo install` bootstrap, which needs the Rust toolchain on PATH and live network reachability to
crates.io/GitHub at mission-`up` time, today (`spawn.py`:385-399).

#### 5.2.3 Pinning in lockstep

`@zico/bob-darwin-arm64`'s version tracks `@zico/bob`'s exactly (section 8), never semver-ranged. The
`optionalDependencies` entry in `@zico/bob`'s `package.json` pins the exact version string
(`"@zico/bob-darwin-arm64": "1.0.0"`, not `^1.0.0`), so `npm update -g @zico/bob` can never resolve a
platform package built by a different bob release than the main package it's paired with - the
esbuild-style lockstep pattern (5.1) applied to versioning, and the mechanism that makes section 8's
"one version number" claim enforceable by npm itself, not just by convention.

### 5.3 Platform coverage

Position: v1 is darwin-arm64 ONLY. It is the sole proven target, and spawn.py's per-mission
sandbox is Apple `container` (macOS-only), so the mission-spawning half cannot run on linux
without a different sandbox backend regardless of how the binaries ship. `bob doctor` fails
fast with a clear platform message on any other host. Linux (glibc + KVM, which microsandbox
itself supports) is a named follow-up, gated on a linux mission-sandbox backend - out of v1.

### 5.4 The microsandbox runtime install (the second "hard part")

The microsandbox libkrun runtime (2.2) is not an npm-shippable binary - it is a VM runtime installed
to `~/.microsandbox`, and it is the one piece bundle-everything cannot literally put in the tarball.
`agent/sandbox.ts` pins `microsandbox({ setup: { autoInstall: true } })`, but that self-heals only
under `eve dev`; `eve start` (what `bob up` runs) fails at sandbox prewarm if the runtime is absent
(`agent/sandbox.ts`, and `HOST-RUN-PLAYBOOK.md`:263-265, which documents today's manual `npx eve
dev` workaround). So bob's own `init`/`doctor` must trigger the install, not eve.

Two candidate handles:

- **(a) A scripted throwaway `eve dev` boot** (start it headless, wait for the ready marker, kill
  it) - mechanically works (it is what a human does by hand today) but is indirect: it boots an
  entire dev server, with its own port/log-file/readiness-race management, purely as a side channel
  to trigger a library's internal auto-install path that is not a documented public API - fragile
  against any future eve change to `eve dev`'s startup sequence, and slow.
- **(b) microsandbox's own public installer, independent of eve**: `curl -fsSL
  https://install.microsandbox.dev | sh` [source 9], which resolves to `scripts/install.sh` in the
  microsandbox repo [source 10]. Read directly, the script detects platform (macOS Apple Silicon
  ONLY - it explicitly REJECTS x86_64 macOS with "Microsandbox requires Apple Silicon (M1+)" - or
  Linux x86_64/aarch64 with glibc >=2.39), installs unprivileged to `$MSB_HOME` (default
  `~/.microsandbox` - the exact directory `autoInstall` also targets), is idempotent, and is fully
  non-interactive.

Position: **(b) is the correct handle.** It installs the exact same runtime `autoInstall` would,
without depending on eve's undocumented internal trigger, without booting a throwaway server, and is
faster and more legible in `bob init` output. Its own platform gate (macOS Apple Silicon only) is
independent third-project confirmation of this RFC's darwin-arm64-only v1 (5.3). `bob init`/`bob
doctor` shell out to that installer (a pinned copy of `install.sh` can be vendored inside `@zico/bob`
for supply-chain hygiene, though the script still needs network to fetch the `msb`/`libkrunfw`
binaries - the same precondition `eve dev`'s auto-install would have had), after checking whether
`msb`/`microsandbox` is already on PATH (skip if present). On an unsupported host, the failure path
is section 5.3's single platform message - one code path whether npm's `os`/`cpu` gate rejected the
install or `bob doctor` catches a borderline case (e.g. Rosetta). 7.4 places this step in the
`init`/`doctor` flow; this subsection owns the mechanism.

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

Two risks worth naming rather than hiding (also 11.1, S10 #3): the docs state a key is deactivated
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

### 7.4 The microsandbox install step (where it sits in the flow)

`bob init` and `bob doctor` both run the microsandbox runtime bootstrap as one blocking step
(spinner shown - first install fetches a VM image and can take tens of seconds) before continuing to
the next check. `agent/sandbox.ts` already pins `autoInstall: true`, but that only self-heals under
`eve dev`, never under the `eve start` bob actually runs (2.2) - so bob's own init/doctor is the
thing that has to trigger the install, not eve.

The mechanism is settled in 5.4: bob shells out to microsandbox's own public installer (`curl -fsSL
https://install.microsandbox.dev | sh`, or a pinned vendored copy of that script), NOT a scripted
throwaway `eve dev` boot - it installs the same `~/.microsandbox` runtime directly, is idempotent
and non-interactive, and has a cleaner failure mode. init/doctor first check whether
`msb`/`microsandbox` is already on PATH and skip if so.

The UX contract: on an unsupported host (5.3 - not darwin-arm64) this step fails FAST with the
platform message before attempting any network install; on a supported host, a failure here is
expected to be the single most common first-run failure (it is the one step needing real network I/O
to fetch a VM image), so init/doctor print the exact remediation (`bob init` again, or the manual
installer command as a fallback) rather than a bare stack trace.

## 8. Update and version story

Position: `@zico/bob` and `@zico/bob-darwin-arm64` share ONE version number, bumped together on
every release, exact-pinned to each other via `optionalDependencies` (5.2.3) - the esbuild pattern
[source 4, source 8]. `npm update -g @zico/bob` re-resolves the main package to its new version,
which carries an updated exact `optionalDependencies` pin, which forces npm to update
`@zico/bob-darwin-arm64` to the matching version in the same operation - there is no npm-level way
for the two to desync as long as the pin stays exact and both packages publish atomically from the
same release.

First, the property that makes updates SAFE at all: `npm update -g` replaces the package's install
tree (`@zico/bob` and its platform package) wholesale, but touches NOTHING under `state_dir` (7.1,
default `~/.local/state/bob`), which is where `.workflow-data`, the orbal-net db/token, and logs
live (section 3). This separation is exactly WHY the durable all-day session survives an update -
the headline feature would be destroyed on every `npm update -g` if any of that state were written
inside the package dir, as `bin-bob.sh` does today (repo-root-relative). State outside the package,
payload inside it: that is the whole update contract.

Four things move together; only one is npm-native, the other three are bob's own coherence claims
that `bob doctor` must actively verify post-update, since npm has no mechanism to guarantee them:

1. **bob JS** (the main package version) - npm-enforced via the exact `optionalDependencies` pin,
   above.
2. **Native binaries** (`herdr`, `orbal-net` inside `@zico/bob-darwin-arm64`) - npm-enforced the same
   way; what npm does NOT catch is a release where the platform package's binaries were built from a
   different `herdr`/`orbal-net` source revision than intended (a release-process bug, not an npm
   problem) - `bob doctor` reports each binary's own `--version` output so a human can check it
   against the release notes.
3. **The `eve` pin** (4.3) - bumped ONLY deliberately, in a commit that also regenerates `.output/`
   (4.2) against the new `eve`, never left to float. `bob doctor` reports the bundled
   `node_modules/eve` version and compares it to what the release manifest (`@zico/bob`'s own
   installed `package.json`) declares - a mismatch means someone modified the installed package's
   `node_modules` by hand (a corrupted/partial `npm update -g` is a real failure mode).
4. **The vendored `spawn.py`/`plan_pane.py` snapshot** (section 6) - refreshed per bob release via the
   scripted `vendor-sync`, carrying its own `.botfiles` source-commit SHA in `vendor/PROVENANCE`. `bob
   doctor` prints that SHA; there is no "correct" SHA to check it against automatically (the canonical
   `.botfiles` repo is a moving target this package has no live access to), so this is a REPORT, not a
   pass/fail - it makes drift visible (section 6's named risk) rather than silently invisible.

What breaks if any one drifts: (1)/(2) drifting is prevented by npm mechanics. (3) drifting (someone
force-installs a different `eve` into an already-installed `@zico/bob`) reintroduces exactly the
beta-churn risk `bundledDependencies` was chosen to eliminate (4.3) - `.output` was built against the
pinned version, so a swapped-in `eve` can boot while serving routes `.output` doesn't expect, or fail
`eve start` outright; `bob doctor`'s version-mismatch report is the only defense, since npm won't stop
a manual `node_modules` edit. (4) drifting means a bob release is running orchestration logic
(`spawn.py`) older than what `.botfiles` has since fixed - not a crash, but a silent capability/bugfix
lag (section 6's named cost), which is why `bob doctor` surfaces the SHA. `bob update` (7.3) chains
`npm i -g @zico/bob@latest` then `bob doctor` automatically, so a bump always lands verified-coherent
rather than leaving the operator to remember the doctor step.

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

Two host prerequisites this RFC does not remove (S10 #6): Node >=24 and `gh` (authenticated) must
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
2. **herdr has no build/release path in the grounding set** (5.1). `orbal-net` is a documented Rust
   crate (`cargo install orbal-net`); `herdr` appears nowhere in `provision.sh`, the Containerfile,
   or any install doc - it is simply assumed on PATH. The optionalDependencies mechanism (5.2) only
   needs herdr as a compiled per-platform executable to vendor, but the release CI cannot vendor a
   binary it has no way to build. Confirming herdr's source/build and producing a darwin-arm64
   binary bob's release pipeline can pull is a hard PRECONDITION of shipping the platform package at
   all - ranked second only to state_dir because it blocks the build itself, not just correctness.
3. **The AI Gateway API key (7.2) is tied to the Vercel account that created it.** Vercel's own docs
   warn a key is deactivated when its creating team member leaves the team - a `bob login` key minted
   under one operator's personal login is a standing organizational risk, not a one-time setup
   detail. Needs investigating whether `zico-ios-projects` has (or should have) a team/bot Vercel
   identity to mint bob's key under, before `bob login` ships as designed.
4. **The microsandbox install mechanism (5.4/7.4) is confirmed on paper, not in a real `bob init`
   run.** The position is settled (microsandbox's own `install.microsandbox.dev` installer over the
   `eve dev`-boot trick, 5.4), but it has not been exercised end to end from an automated
   `init`/`doctor`; the exact failure UX when the installer's network fetch fails is the single most
   likely first-run failure and should be validated against a real cold host before build.
5. **spawn.py drift (S6) is invisible unless `bob doctor` is run habitually.** The vendored copy is
   the default for every `npm i -g` host, and the only drift signal is `doctor`'s provenance-SHA
   check - a host that never runs `doctor` never learns it has fallen behind `.botfiles`. Consider
   surfacing the provenance SHA in `bob status` too (2.1's most-run command), not only
   `doctor`/`version`.
6. **`gh` auth and Node >=24 stay unmanaged host prerequisites** (9.1) - `init`/`doctor` check but
   never install either. Consistent with how npm-global CLIs usually treat host toolchain, but
   should be stated as a deliberate non-goal so "bundle-everything" doesn't get read as "bundles the
   host's own package managers too."
7. **`bob login` (7.2) itself needs a Vercel CLI or REST dependency decision.** Minting a key via
   `vercel ai-gateway api-keys create` needs the Vercel CLI on the host (another native dependency to
   pin, akin to S5's herdr/orbal-net) or a hand-rolled call against the REST `POST /v1/api-keys`
   endpoint using a Vercel personal access token (fewer moving parts, but a worse first-run UX - the
   operator needs to mint that token first). Leans REST but is a real design decision, not just a
   citation, and isn't made here.
8. **Should `bob init` set a spend budget on the AI Gateway key it mints by default?** An unattended,
   all-day orchestrator holding an unbounded non-expiring key is a real cost-runaway risk (7.2). A
   conservative default budget with a `bob init --budget <amount>` override is proposed but is a
   product call (what "conservative" means for this team), not an engineering one.

### The recommended first build increment

Do not build all of bob-cli at once. The first increment is the smallest slice that proves the
thesis end to end on the proven platform, and it is deliberately NOT the hard parts:

**Increment 1 - "the package boots on one host."** Publish `@zico/bob` + `@zico/bob-darwin-arm64` to
a private registry, carrying: the ported `bin/bob` node entry (S3), the prebuilt `.output` +
bundled `eve@0.22.1` (S4), the vendored `orbal-net` binary in the platform package (S5 - orbal-net
only, since its build path IS known; herdr deferred to increment 2 pending open question #2), the
`~/.config/bob/config.toml` writer and `state_dir` separation (7.1, and the state-outside-package
property is proven HERE because it is the riskiest single decision, #1), and `bob init` doing just
three things: write the config, run `bob login` to mint the long-lived AI Gateway key (7.2, killing
the OIDC re-link - the sharpest user win, proven early), and run the microsandbox installer (5.4).
Acceptance: on a fresh darwin-arm64 host with zero `.botfiles` clone, `npm i -g @zico/bob && bob
init && bob` brings up the durable TUI, a codeword survives `bob down`/`bob up` (the durability
property, now that state lives in `state_dir`), and no `vercel link` is ever run. This proves the
three highest-load-bearing decisions (state_dir survival, OIDC kill, prebuilt-boot) in one slice
while leaving herdr, full `bob doctor` drift-checks, and any second platform to follow-on
increments. It is the increment a build lead can start on Monday with no blocked precondition except
resolving open question #2 (herdr) in parallel before it gates spawning a real fleet.

## 11. Appendix

### 11.1 Beta-churn risk register

| Dependency | Churn it can throw | bob's containment |
|---|---|---|
| eve (Vercel beta) - version | Patch-level drift is real and observed: `eve` moved `0.22.1` -> `0.22.4` [source 1] while this RFC was drafted; an unpinned dependency could pull an untested build. | Exact pin (`eve@0.22.1`) travelling as `bundledDependencies` (4.3), so a user's `eve` only changes when a bob release changes it; `.output` is rebuilt against the new pin in the same commit (4.2). |
| eve - `.output` build-output shape | `eve build`'s output structure could change between versions, breaking a prebuilt `.output` served by a different `eve`. | Prebuilt `.output` + bundled `eve` are always the pair CI tested (4.5); `bob doctor --rebuild` (4.4) regenerates locally if a host still fails. |
| eve - `eve start` runtime behavior | Sandbox-prewarm / session-resume semantics could shift under a beta patch, independent of `.output` shape. | Contained by the exact pin at any point in time; residual risk flagged - bob does not control eve's breaking-change discipline (4.5). |
| eve - microsandbox autoInstall trigger | `autoInstall` fires only under `eve dev` today (2.2); the trigger condition is undocumented and could change. | bob does NOT depend on it - it drives microsandbox's own public installer directly (5.4), decoupling install from any eve-internal behavior. |
| Vercel AI Gateway auth (beta surface) | A future `ai` SDK major could change the `AI_GATEWAY_API_KEY || VERCEL_OIDC_TOKEN` precedence 7.2 relies on; the leaver-deactivation policy (a key dies if its creating team member leaves) is a standing, not one-time, risk. | `bob doctor`'s key-liveness probe (7.3) turns any future auth break into a diagnosed failure with a `bob login --rotate` remediation, never a silent eve boot failure; open question #3 tracks minting under a team/bot identity. |
| microsandbox (young project) | Installer script / `$MSB_HOME` layout / platform gate could change; libkrun runtime is macOS-Apple-Silicon or glibc-Linux+KVM only. | A pinned vendored copy of `install.sh` (5.4) freezes the install behavior bob tested; its platform gate matches bob's own darwin-arm64 v1 (5.3). |
| Apple `container` (spawn.py mission sandbox, young) | The per-mission microVM CLI (`container`) is macOS-only and young; its CLI surface could shift. | Out of this RFC's scope to re-architect (a non-goal); it is why v1 is darwin-arm64 (5.3), and it is consumed by the vendored `spawn.py` as-is (section 6). |

### 11.2 Sources

Numbered to match the `[source N]` citations in the body. eve/npm/Vercel-auth/microsandbox claims
each cite a row here.

1. `github.com/vercel/eve` - repo landing page: confirms `eve@0.22.4` is current tip (checked
   2026-07-10) against the `0.22.1` this RFC pins, and that eve is explicitly "in beta ... the
   framework, APIs, documentation, and behavior may change before general availability." Proves the
   beta-churn claim with a live version-drift example.
2. `docs.npmjs.com/cli/v10/configuring-npm/package-lock-json` - "`package-lock.json` cannot be
   published, and it will be ignored if found in any place other than the root project"; documents
   `npm-shrinkwrap.json` as the one publishable exception. Proves a published package's own lockfile
   does not give a global install of that package deterministic transitive resolution.
3. `docs.npmjs.com/cli/v10/configuring-npm/package.json#bundledependencies` - defines
   `bundledDependencies`: listed packages are embedded in the published tarball (via `npm
   pack`/`publish`) and extracted as-is on install rather than re-fetched. Grounds 4.3 (eve travels
   via `bundledDependencies`).
4. `unpkg.com/esbuild@latest/package.json` - esbuild's real `package.json`: ~25
   `optionalDependencies`, one per platform, all pinned to the exact same version as the main
   package. Grounds the "esbuild pattern" cited in 5.1/5.2/8.
5. `unpkg.com/@esbuild/darwin-arm64@latest/package.json` - the platform package's manifest:
   `"os": ["darwin"]`, `"cpu": ["arm64"]`, no `bin` field. Grounds 5.2's platform-package shape.
6. `docs.npmjs.com/cli/v10/configuring-npm/package.json#optionaldependencies` - a failed/skipped
   optional dependency does not fail the parent install; npm preserves the executable bit through the
   publish/install cycle. Grounds 5.2/5.2.1.
7. `docs.npmjs.com/cli/v10/configuring-npm/package.json#cpu` (and adjacent `#os`) - host OS is
   `process.platform`, host arch is `process.arch`. Grounds how npm decides to install an
   `os`/`cpu`-gated optional dependency.
8. `github.com/evanw/esbuild/issues/789` - the discussion where esbuild's per-platform
   `optionalDependencies` split was worked out vs. vendoring every arch in one tarball. Grounds the
   "vendored-in-main-tarball is the anti-pattern" claim in 5.2.
9. `microsandbox.dev` - publishes the one-line installer `curl -fsSL https://install.microsandbox.dev
   | sh`. Grounds 5.4/7.4.
10. `raw.githubusercontent.com/superradcompany/microsandbox/refs/heads/main/scripts/install.sh` - the
    installer script: platform gate (macOS Apple Silicon only / Linux x86_64+aarch64 glibc >=2.39,
    explicit x86_64-macOS rejection), install location (`$MSB_HOME`, default `~/.microsandbox`),
    unprivileged, idempotent, non-interactive. Grounds the "install.sh over `eve dev` boot" position
    (5.4) and the darwin-arm64 platform confirmation.
11. `eve.dev/docs/guides/deployment` - `eve build`'s output structure (`.output/` = "standard Nitro
    output" for self-hosted `eve start`) and "eve runs the same way locally, on Vercel, and on a
    long-running Node host." Grounds 4.1/4.2's characterization of `.output/`.
12. `vercel.com/docs/ai-gateway/authentication-and-byok/oidc` - OIDC token lifetime (12h in local
    dev, shorter in prod/preview) and that `vercel link` + `vercel env pull` is the only refresh path.
    Grounds 2.3/7.2 (why the OIDC token forces the hourly re-link).
13. `vercel.com/docs/ai-gateway/authentication-and-byok` - API keys never expire unless revoked; the
    AI SDK's `AI_GATEWAY_API_KEY || VERCEL_OIDC_TOKEN` precedence; the leaver-deactivation caveat.
    Grounds 7.2's OIDC-kill position and 11.1's auth risk row.
14. `vercel.com/docs/ai-gateway/authentication-and-byok/api-keys` - `vercel ai-gateway api-keys
    create` CLI, one-time secret reveal, id-based list/delete, optional budget/`expiresAt`. Grounds
    the `bob login` / `bob login --rotate` / budget design in 7.2/7.3 and open questions #7/#8.
