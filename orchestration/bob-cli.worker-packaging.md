# worker-packaging deliverable - sections 3, 4, 5, 8 + microsandbox install mechanism (feeds 7.4)

Prose below is meant to be pasted into the matching marked sections of `orchestration/bob-cli.rfc.md`.
Written directly to this file (not edited into the shared RFC) since worker-ux is editing the same
file concurrently and we share one clone - avoids clobbering their in-flight edits. Citations are
inline as `[source N]`; the numbered list at the bottom is ready to fold into 11.2.

---

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
│   │   └── host-exec.ts         # orchestrationDir() default becomes vendor/ (see section 6 and
│   │                             #   worker-ux's 7.1), not /opt/botfiles/orchestration
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
├── node_modules/                 # BUNDLED (bundledDependencies, 4.3) - eve@0.22.1's full
│   └── ...                       #   resolved tree, shipped inside the tarball itself
└── package.json
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
doctor` (worker-ux, 7.3) still exists for a borderline host that gets past npm's gate (e.g.
Rosetta), but npm's own platform check is the first, cheapest line of defense - free, and fires
before a single byte of the package downloads.

End state: `npm i -g @zico/bob` places exactly two package directories under npm's global
`node_modules`, one `bob` symlink on PATH, and every artifact bob needs already on disk - no
postinstall network fetch beyond npm's own package resolution (everything else is bundled or
`bundledDependencies`), no separate `cargo install`, no separate download for `herdr`/`orbal-net`.

### 3.1 Package payload vs. mutable runtime state (load-bearing for section 8)

Everything in the tree above is the PACKAGE PAYLOAD - npm-owned, read-only in practice, and
REPLACED wholesale on every `npm i -g @zico/bob@<newer>` / `npm update -g @zico/bob` (npm does not
diff-patch a global install; it removes the old package directory contents and writes the new
package's files in its place). That is fine for everything listed in the tree - `agent/`,
`.output/`, `vendor/`, the platform package's binaries are all meant to be replaced on update. It
is NOT fine for what `bin/bob` (bin-bob.sh today) currently writes: the durable eve session store
(`.workflow-data` - the ALL-DAY conversation `bin/bob` explicitly never wipes), the shared
`orbal-net serve` state (`.bob-orbal-net.db`, `.bob-orbal-net.token`), and the process logs
(`.bob-eve.log`, `orbal-net-connector.log`, `.bob-orbal-net.log`) - `bin-bob.sh` writes every one
of these repo-root-relative (`cd "$(dirname "$0")/.." ; ... "${BOB_EVE_LOG:-.bob-eve.log}"` etc.
[reference/bob-repo/bin-bob.sh:38,41-42,61-63]) because in the dev-repo world the repo root IS the
one stable, human-owned directory. A globally-installed npm package has no such directory - its
"root" is npm-managed and gets replaced out from under any file written there.

Position: split package payload from mutable state at the top level. The package payload lives
under npm's global `node_modules/@zico/bob/` (the tree above, unchanged); ALL mutable
runtime state moves to `state_dir` (worker-ux's 7.1 config field, default `~/.local/state/bob`,
XDG-conventional and outside every npm-managed directory):

```
~/.local/state/bob/                 # state_dir - NEVER touched by npm, survives every update
├── .workflow-data/                 # the durable eve session store (bin-bob.sh's "never wipe" file)
├── orbal-net.db                    # was .bob-orbal-net.db - shared server's room/message state
├── orbal-net.token                 # was .bob-orbal-net.token - persisted server auth token, 0600
└── logs/
    ├── eve.log                     # was .bob-eve.log
    ├── connector.log                # was orbal-net-connector.log
    └── orbal-net-server.log         # was .bob-orbal-net.log
```

`bin/bob`'s ported entry (S3's `bin/bob`) resolves `state_dir` from config (env override > config
> `~/.local/state/bob` default, worker-ux's 7.1 precedence) and points every one of these paths at
it instead of a repo-root-relative default - a one-line change in KIND from today's `bin-bob.sh`
(the variables `EVE_LOG`/`SERVER_TOKEN_FILE`/`SERVER_DB`/`SERVER_LOG` already exist as overridable
env vars today [reference/bob-repo/bin-bob.sh:41-42,61-63]; packaging just changes their default
from repo-root-relative to `state_dir`-relative). This is why section 8's update story can claim
the durable session survives `npm update -g` - it is a structural property of WHERE state lives,
not a promise `bob doctor` has to enforce after the fact.

---

## 4. The eve-app bundle: PREBUILT .output (decided)

(Position paragraph is already locked in the skeleton - the following fills the tradeoff,
mechanics, and escape hatch underneath it.)

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
the project directory (the RFC's own locked framing: "`eve start` serves `.output` but needs the
project"), so `agent/` (the eve project itself: `sandbox.ts`, `lib/`, `tools/`) ships as real
TypeScript source next to `.output/`, unchanged from the repo, read by `eve start` at boot even
though it is never recompiled there. `connector/main.ts` and `client/bob-tui.ts` are NOT
eve-compiled at all - they are the plain Node entry points `bin/bob` already runs today via `node
--experimental-strip-types connector/main.ts` / `client/bob-tui.ts` [reference/bob-repo/bin-bob.sh:177,187],
so they ship as `.ts` source and run identically post-packaging. Nothing here is stripped down
for the package: the same three source trees (`agent/`, `connector/`, `client/`) that exist in the
repo today ship byte-for-byte inside `@zico/bob`; `.output/` is the one genuinely NEW artifact,
generated once at release time, not per install.

### 4.3 How eve@0.22.1 travels

`eve` stays an ordinary `"dependencies"` entry, pinned EXACT (`"eve": "0.22.1"`, no `^`) - it is a
Vercel beta and churns across even patch versions (`0.22.4` is current tip as of this research,
against the `0.22.1` this RFC pins [source 1]). An exact pin in `dependencies` is not, by itself,
enough for a GLOBAL install to be fully deterministic: `npm i -g` resolves `@zico/bob`'s
dependency tree fresh against the registry using ordinary semver resolution, and a published
package's own `package-lock.json` is explicitly NOT consulted when that package is installed as a
dependency of something else (global or local) - npm's docs state it directly: "`package-lock.json`
cannot be published, and it will be ignored if found in any place other than the root project"
[source 2]. (The one publishable exception, `npm-shrinkwrap.json`, pins resolution but still
fetches from the registry at install time - no offline benefit, no immunity if `eve` is ever
unpublished/deprecated - so it doesn't fully close this gap either.) So `eve@0.22.1`'s own
transitive tree can drift release to release even with bob's own pin held constant.

Position: mark `eve` (and its co-pinned direct deps `ai`, `@vercel/connect`, `zod`)
`bundledDependencies` [source 3] in `@zico/bob`'s `package.json`. `npm pack`/`npm publish` then
embeds a real, fully-resolved `node_modules/` snapshot inside the published tarball itself; on
`npm i -g`, npm extracts that snapshot as-is instead of re-resolving from the registry [source 3].
This is the strongest determinism npm offers: the exact `eve@0.22.1` plus its exact transitive
tree that bob's release CI built `.output` against is what every user gets, byte-for-byte,
forever - immune to `eve` being unpublished/deprecated/patched out from under a later install, and
installable fully offline. The cost is tarball size (a full `node_modules/eve` plus its deps,
plausibly tens of MB) - acceptable under the decided bundle-everything thesis (section 1), and no
larger in kind than what `optionalDependencies` already commits to for the native platform package
(section 5).

### 4.4 The `bob doctor --rebuild` escape hatch

Shipping `.output/` prebuilt does not remove the ability to rebuild locally. `bob doctor --rebuild`
runs `eve build` against the shipped `agent/` source in place (using the bundled `eve` from
`node_modules/` - no extra install), overwriting that package's own `.output/` inside the global
install directory. This exists for two cases only: (a) a host where the prebuilt `.output` fails
to boot for a reason CI didn't catch (a Node minor-version quirk, a corrupted global install), and
(b) a bob developer pointed at a live source checkout via an `ORCHESTRATION_DIR`-style override,
who needs local edits reflected without cutting a release. It is explicitly NOT the default path -
section 4.1's entire argument is that build-on-install-by-default is the rejected option - so it is
gated behind an explicit flag; a plain `npm i -g` / `bob init` never triggers it silently.

### 4.5 Beta-churn caveat (feeds 11.1)

A prebuilt `.output` couples every bob release to the exact `eve` build-output shape at the moment
of that release. `bundledDependencies` (4.3) prevents the sharpest version of this risk (a user's
installed `eve` version only ever changes when a bob release changes it, so `.output` and its
`eve` are always the pair CI tested). The residual risk is narrower: `eve start`'s runtime
*behavior* (not the `.output` shape) changing between eve versions bob has pinned across releases -
contained by the exact pin at any single point in time, but still a beta dependency whose release
cadence and breaking-change discipline this RFC does not control.

---

## 5. Bundling the native orchestration binaries (herdr, orbal-net)

### 5.1 What "native binary" actually means here, today

The two are not symmetric in the grounding material. `orbal-net` is documented end to end: one
Rust binary, published at `github.com/zico-io/orbal-net`, distributed via `cargo install
orbal-net` (falling back to `cargo install --git ...` until a crates.io release lands)
[.botfile/memory/tools/orchestration.md]. `spawn.py`'s own `_ensure_orbal_net()` performs exactly
this bootstrap today on the host [orchestration/spawn.py:385-399], and the sandbox image's
Containerfile does the guest-side equivalent at build time [sandbox/Containerfile:45-53]. `herdr`
has NO equivalent install path anywhere in this mission's grounding set - it is assumed already on
PATH (`HOST-RUN-PLAYBOOK.md` prerequisites, the `HERDR_ENV=1` precondition) and never appears in
`provision.sh` or the Containerfile.

This RFC's packaging mechanism (5.2) does not need to know herdr's build toolchain - it only needs
herdr as a compiled, `chmod +x`, per-platform executable to vendor, exactly like `orbal-net`.
Flagged explicitly rather than waved through: herdr's actual build/release process is UNVERIFIED
against source in this mission's grounding set, and either confirming it or getting per-platform
herdr binaries bob's release CI can pull is a real precondition of implementation (feeds section 10
and 11.1), not a packaging detail this RFC can resolve from what it was given to read.

### 5.2 Distribution mechanism: per-platform optionalDependencies (the esbuild pattern)

Position: `@zico/bob` never runs `cargo install` or downloads anything at install time. It ships
`herdr` + `orbal-net` as prebuilt executables inside a separate, platform-scoped npm package
(`@zico/bob-darwin-arm64`, section 3), declared as an `optionalDependency` of the main package.
This is the same mechanism esbuild uses for its ~25 platform binaries [source 4]:
`@esbuild/darwin-arm64@0.28.1`'s `package.json` carries `"os": ["darwin"], "cpu": ["arm64"]` and no
other gating [source 5]; npm's installer reads those fields against `process.platform`/
`process.arch` [source 6, source 7] and silently skips installing any optional dependency whose
`os`/`cpu` doesn't match the current host - a skipped/failed optional dependency does not fail the
parent install, that is the entire point of `optionalDependencies` [source 6]. A `darwin-arm64`
host installs `@zico/bob-darwin-arm64` and nothing else; any other host (once a second platform
package exists, 5.3) installs neither and moves on.

Compared to the two alternatives named in the brief:

- **postinstall-download of a pinned release** (a `postinstall` script that curls a GitHub release
  asset for the detected platform): adds a runtime network dependency to every single install
  (fails offline, fails behind a mirror/proxy that blocks arbitrary GitHub hosts), and moves
  integrity verification into hand-rolled script code (checksum it yourself, decide what
  "verified" means, handle partial/corrupt downloads) instead of npm's own tarball integrity (npm
  computes and the registry serves an integrity hash npm verifies automatically on every install -
  no extra code needed). This is, in effect, what `orbal-net`'s CURRENT distribution
  (`cargo install`) already is - a build/download at install time - and it is exactly the
  fragility (network dependency, `cargo`-on-PATH precondition, a "tried crates.io and git, install
  manually" failure message [orchestration/spawn.py:385-399]) that bundle-everything (section 1)
  exists to eliminate.
- **vendored in the main tarball** (ship `herdr`+`orbal-net` binaries for every supported platform
  directly inside `@zico/bob`, no separate package): every install downloads every platform's
  binary regardless of host, bloating a darwin-arm64 user's install with binaries they can never
  run the moment a second platform ships. Harmless functionally, wasteful in bandwidth/disk, and
  is the anti-pattern esbuild's own platform-package split was created specifically to move away
  from [source 8].

v1 ships only `@zico/bob-darwin-arm64`, so the bandwidth argument is currently moot (there is only
one platform package to install), but the shape is chosen now, not deferred: it is the only one of
the three that survives adding a second platform (5.3's named Linux follow-up) without an npm
package restructure - add `@zico/bob-linux-x64` as a sibling package plus one more
`optionalDependencies` entry; `@zico/bob`'s own shipped files never change.

#### 5.2.1 Resolution and exec at runtime

`@zico/bob-darwin-arm64` carries no `"bin"` field of its own - a platform package is not
independently useful, only a payload the main package reaches into. `bin/bob` (the main package's
entry, section 3) resolves the two binaries the same way esbuild's JS wrapper resolves its native
binary: via `require.resolve`/`import.meta.resolve` against `@zico/bob-darwin-arm64`'s known
package name, not by assuming a bare `herdr`/`orbal-net` is already on PATH. `bin/bob` then either
execs them directly by absolute path (e.g. `orbal-net serve` at `bob up`) or PREPENDS that
platform package's `bin/` directory onto `PATH` for the process tree it spawns - so `spawn.py`'s
own `shutil.which("orbal-net")` check [orchestration/spawn.py:392] and every `orbal-net <cmd>` a
lead/worker types keep working completely unmodified; no changes needed inside `spawn.py` or the
harness bootstrap prompts. The vendored binaries are marked executable (`chmod +x`) at PUBLISH
time, as part of the release pipeline that produces `@zico/bob-darwin-arm64`'s tarball, not on
install - npm preserves the executable bit through pack/publish/install for files under `bin/`
[source 6], the same guarantee esbuild's own binary packages rely on.

#### 5.2.2 Offline-install story

Because both binaries are inside a tarball npm already fetched (no separate download, no `cargo
install`, no postinstall network call), `npm i -g @zico/bob` is fully offline-capable from an
npm-compatible mirror/cache the moment both package tarballs are in it - the same offline story
`bundledDependencies` gives `eve` (4.3). This is the concrete improvement over `orbal-net`'s
CURRENT `cargo install` bootstrap, which needs the Rust toolchain on PATH and live network
reachability to crates.io/GitHub at mission-`up` time, today [orchestration/spawn.py:385-399].

#### 5.2.3 Pinning in lockstep

`@zico/bob-darwin-arm64`'s version tracks `@zico/bob`'s exactly (section 8), never semver-ranged.
The `optionalDependencies` entry in `@zico/bob`'s `package.json` pins the exact version string
(`"@zico/bob-darwin-arm64": "1.0.0"`, not `^1.0.0`), so `npm update -g @zico/bob` can never resolve
a platform package built by a different bob release than the main package it's paired with - the
esbuild-style lockstep pattern (5.1) applied to versioning, and the mechanism that makes section
8's "one version number" claim enforceable by npm itself, not just by convention.

(5.3 Platform coverage is already locked in the skeleton - untouched.)

---

## 8. Update and version story

Position: `@zico/bob` and `@zico/bob-darwin-arm64` share ONE version number, bumped together on
every release, exact-pinned to each other via `optionalDependencies` (5.2.3) - the esbuild pattern
[source 4, source 8]. `npm update -g @zico/bob` re-resolves the main package to its new version,
which carries an updated exact `optionalDependencies` pin, which forces npm to update
`@zico/bob-darwin-arm64` to the matching version in the same operation - there is no npm-level way
for the two to desync as long as the pin stays exact and both packages publish atomically from the
same release.

`npm update -g` only ever touches the PACKAGE PAYLOAD (npm's global `node_modules/@zico/bob/` and
`node_modules/@zico/bob-darwin-arm64/`, both wholesale-replaced) - it has no reason to, and no
mechanism to, touch `state_dir` (3.1, default `~/.local/state/bob`), because nothing under
`state_dir` is part of either npm package. This is WHY the durable all-day session
(`.workflow-data`), the shared `orbal-net` server's room/message history (`orbal-net.db`), and its
persisted auth token survive a `bob` update untouched - not a promise layered on top, but a direct
consequence of 3.1's payload/state split. The only thing worth `bob doctor` checking here is the
inverse failure mode: confirm `state_dir` is NOT accidentally nested inside the npm package
directory (a config or install regression that would silently reintroduce the destroy-on-update bug
this split exists to prevent).

Four things move together; only one is npm-native, the other three are bob's own coherence claims
that `bob doctor` must actively verify post-update, since npm has no mechanism to guarantee them:

1. **bob JS** (the main package version) - npm-enforced via the exact `optionalDependencies` pin,
   above.
2. **Native binaries** (`herdr`, `orbal-net` inside `@zico/bob-darwin-arm64`) - npm-enforced the
   same way; what npm does NOT catch is a release where the platform package's binaries were built
   from a different `herdr`/`orbal-net` source revision than intended (a release-process bug, not
   an npm problem) - `bob doctor` reports each binary's own `--version` output so a human can check
   it against the release notes.
3. **The `eve` pin** (4.3) - bumped ONLY deliberately, in a commit that also regenerates `.output/`
   (4.2) against the new `eve`, never left to float. `bob doctor` reports the bundled
   `node_modules/eve` version and compares it to what the release manifest (embedded in
   `@zico/bob`'s own installed `package.json`, read at doctor-time) declares it should be - a
   mismatch means someone modified the installed package's `node_modules` by hand (unsupported, but
   worth detecting: a corrupted/partial `npm update -g` is a real failure mode, not a hypothetical
   one).
4. **The vendored `spawn.py`/`plan_pane.py` snapshot** (section 6) - refreshed per bob release via
   the scripted `vendor-sync`, carrying its own `.botfiles` source-commit SHA in `vendor/PROVENANCE`
   (section 6). `bob doctor` prints that SHA; there is no "correct" SHA to check it against
   automatically (the canonical `.botfiles` repo is a moving target this package has no live access
   to), so this is a REPORT, not a pass/fail - it makes drift visible (section 6's named risk)
   rather than silently invisible, which is the most `bob doctor` can honestly promise without
   giving bob a network call into `.botfiles`'s own commit history.

What breaks if any one drifts: (1)/(2) drifting is prevented by npm mechanics, not a runtime
failure mode this design needs to defend against further. (3) drifting (someone force-installs a
different `eve` version into an already-installed `@zico/bob`) reintroduces exactly the beta-churn
risk `bundledDependencies` was chosen to eliminate (4.3) - `.output` was built against the pinned
version, so a swapped-in `eve` can boot successfully while serving routes `.output` doesn't expect,
or fail `eve start` outright; `bob doctor`'s version-mismatch report is the only defense, since npm
itself won't stop a manual `node_modules` edit. (4) drifting means a bob release is running
orchestration logic (`spawn.py`) older than what `.botfiles` has since fixed - not a crash, but a
silent capability/bugfix lag (section 6's named cost), which is why `bob doctor` surfaces the SHA
rather than pretending the vendored copy is always current.

`bob doctor` itself (worker-ux, section 7.3) is where all four checks surface to the user; this
section's job is only to establish that the four things exist, why they can drift independently,
and which of the four npm's own version mechanics actually close off versus which stay bob's
responsibility to detect.

---

## Microsandbox install mechanism (confirms 5.2's pattern, feeds section 7.4 - worker-ux places this in init/doctor UX; I own the mechanism)

CONFIRMED, independently of worker-ux's own finding (same conclusion, reached separately before
comparing notes): the public installer, not a scripted `eve dev` boot, is the pick for both 5.2
(this is the same "don't shell out through an undocumented internal trigger when a project ships a
real installer" logic 5.2 already applies to `herdr`/`orbal-net`) and 7.4 (where worker-ux wires it
into `bob init`/`bob doctor`).

Grounded in `agent/sandbox.ts`: `defineSandbox({ backend: microsandbox({ setup: { autoInstall:
true } }) })` [reference/bob-repo/agent/sandbox.ts:1-22]. The file's own comment matches exactly
what this RFC needs to design around: `setup.autoInstall` "lets eve install the microsandbox VM
runtime (libkrun) on first boot if it is missing," but "only `eve dev` auto-installs" - `eve start`
(what `bob up` runs, production) "fails at sandbox prewarm with an install error instead of
auto-installing." `HOST-RUN-PLAYBOOK.md`'s troubleshooting section confirms the current workaround
is manual: run `npx eve dev` once, wait for it to serve, Ctrl-C, the runtime stays installed
[reference/bob-repo/docs/HOST-RUN-PLAYBOOK.md:263-265].

Two candidate install handles for `bob init`/`bob doctor`:

**(a) A scripted throwaway `eve dev` boot** (start it headless, wait for the ready marker, kill
it) - mechanically works (it's what a human does by hand today) but is indirect: it boots an
entire dev server, with its own port/log-file/readiness-race management, purely as a side channel
to trigger a library's internal auto-install path that isn't documented as a public API - fragile
against any future eve change to `eve dev`'s startup sequence or its auto-install trigger
condition, and slow (a real server boot, not a runtime install call).

**(b) The microsandbox project's own public installer, independent of eve entirely**: `curl -fsSL
https://install.microsandbox.dev | sh` [source 9], which redirects to `scripts/install.sh` in the
`microsandbox` GitHub repo [source 10]. Read directly, the script: detects platform (macOS Apple
Silicon ONLY - it explicitly REJECTS x86_64 macOS with the error "x86_64 macOS is not supported.
Microsandbox requires Apple Silicon (M1+)" - or Linux x86_64/aarch64 with glibc >=2.39), installs
unprivileged to `$MSB_HOME` (default `~/.microsandbox/bin` + `/lib` - the exact directory
`agent/sandbox.ts`'s `autoInstall` also targets), symlinks `msb`/`microsandbox` into
`~/.local/bin`, is idempotent (`install(1)` unlinks-then-relinks, so a re-run is safe rather than
erroring on an existing install), and contains no interactive prompts anywhere - safe to shell out
to from an automated `bob init`/`bob doctor` [source 9, source 10].

Position: **(b) is the correct handle, not (a).** It installs the exact same runtime `autoInstall`
would have, without depending on eve's internal (undocumented) auto-install trigger, without
booting a throwaway server, and is faster and more legible in `bob init` output ("installing
microsandbox runtime..." vs. silently spinning up and tearing down an eve dev server the user
never asked to see). Worth noting directly: the installer's own platform gate (macOS Apple Silicon
only, in v1's scope) lines up exactly with this RFC's own darwin-arm64-only v1 decision (section
5.3) - independent confirmation from a THIRD project that darwin-arm64 is the only currently-sane
v1 target for this whole stack, not just bob's own call.

Concretely: `bob init` and `bob doctor` should shell out to that installer script directly
(vendoring a pinned copy of `install.sh` inside `@zico/bob` is consistent with this RFC's
offline-install posture elsewhere, 4.3/5.2.2 - though the script itself still needs network
reachability to fetch the actual `msb`/`libkrunfw` binaries it installs, same precondition
`eve dev`'s auto-install would have had) and should check for `msb`/`microsandbox` already on PATH
first (skip if present - idempotent either way, but avoids a redundant network call on every
`doctor` run). On an unsupported host (anything the installer's own platform check rejects),
`bob init`/`bob doctor` should fail with the SAME clear platform message section 5.3 already
commits to for the darwin-arm64 gate generally - one message, one code path, whether npm's
`os`/`cpu` fields rejected the install outright or `bob doctor` catches a borderline case (e.g.
Rosetta) that got past them.

---

## Sources (feeds 11.2 - numbered as cited above)

1. `github.com/vercel/eve` - repo landing page: confirms `eve@0.22.4` is current tip (checked
   2026-07-10) against `0.22.1` this RFC pins, and that eve is explicitly "in beta and subject to
   the Vercel beta terms; the framework, APIs, documentation, and behavior may change before
   general availability." Proves the beta-churn claim with a live version-drift example, not a
   hypothetical.
2. `docs.npmjs.com/cli/v10/configuring-npm/package-lock-json` - "`package-lock.json` cannot be
   published, and it will be ignored if found in any place other than the root project"; documents
   `npm-shrinkwrap.json` as the one publishable exception. Proves a published package's own
   lockfile does not give a global install of that package deterministic transitive resolution.
3. `docs.npmjs.com/cli/v10/configuring-npm/package.json#bundledependencies` - defines
   `bundledDependencies`/`bundleDependencies`: packages listed are embedded in the published
   tarball (via `npm pack`/`npm publish`) and extracted as-is on install rather than re-fetched
   from the registry. Grounds the 4.3 position (eve travels via `bundledDependencies`, not a bare
   pinned `dependencies` entry).
4. `unpkg.com/esbuild@latest/package.json` - esbuild 0.28.1's real `package.json`: ~25
   `optionalDependencies` entries (one per platform), all pinned to the exact same version as the
   main package, plus a `postinstall` verification script. Grounds the "esbuild pattern" cited
   throughout 5.1/5.2/8 with the actual current manifest, not a paraphrase.
5. `unpkg.com/@esbuild/darwin-arm64@latest/package.json` - the platform package's own manifest:
   `"os": ["darwin"]`, `"cpu": ["arm64"]`, no `bin` field. Grounds 5.2's claim about how a platform
   package is shaped and that it carries no independent `bin` entry.
6. `docs.npmjs.com/cli/v10/configuring-npm/package.json#optionaldependencies` - "If a dependency
   can be used, but you would like npm to proceed if it cannot be found or fails to install" -
   confirms a failed/skipped optional dependency does not fail the parent install, and that npm
   preserves file permissions (executable bit) through the publish/install cycle.
7. `docs.npmjs.com/cli/v10/configuring-npm/package.json#cpu` (and the adjacent `#os` section) -
   "The host operating system is determined by `process.platform`" / "The host architecture is
   determined by `process.arch`" - grounds exactly how npm decides whether to install an
   `os`/`cpu`-gated optional dependency on a given host.
8. `github.com/evanw/esbuild/issues/789` ("Different strategy for installing platform-specific
   binaries") - the historical discussion where esbuild's per-platform `optionalDependencies` split
   was worked out, as the alternative to vendoring every architecture in one tarball. Grounds the
   "vendored-in-main-tarball is the anti-pattern this split was created to avoid" claim in 5.2.
9. `microsandbox.dev` - publishes the one-line installer: `curl -fsSL
   https://install.microsandbox.dev | sh`.
10. `raw.githubusercontent.com/superradcompany/microsandbox/refs/heads/main/scripts/install.sh` -
    the actual installer script: platform gate (macOS Apple Silicon only / Linux x86_64+aarch64
    with glibc >=2.39, explicit rejection message for x86_64 macOS), install location
    (`$MSB_HOME`, default `~/.microsandbox`), unprivileged (no sudo), idempotent, fully
    non-interactive. Grounds the entire "install.sh over a scripted `eve dev` boot" position.
11. `eve.dev/docs/guides/deployment` - describes `eve build`'s output structure (`.eve/` discovery
    manifest always; `.output/` "standard Nitro output" for self-hosted `eve start`; `.vercel/output`
    only when `VERCEL` is set) and states "eve runs the same way locally, on Vercel, and on a
    long-running Node host." Grounds 4.1/4.2's characterization of what `.output/` is and that
    self-hosted portability is a documented eve property, not an assumption.
