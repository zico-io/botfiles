# Mission brief: orbal-net-release

## Goal
Publish the `comms` CLI to public crates.io as `orbal-net`, with a CI/CD pipeline
that tests, builds, and publishes on version tags - and rebrand `comms` -> `orbal-net`
across the codebase. The crate splits out of the private `.botfiles` monorepo into a
new public repo `github.com/zico-io/orbal-net`, which owns its CI and publishing;
`.botfiles` then consumes the tool as an installed binary. Success: `v0.1.0` of
`orbal-net` is live on crates.io from a green pipeline, and the orchestration protocol
runs unchanged on the renamed binary + env vars.

## In scope
- New public repo `zico-io/orbal-net`; crate moved out of `.botfiles` via `git subtree split -P comms` with history preserved.
- Full rebrand: package + binary -> `orbal-net`; env `COMMS_*` -> `ORBAL_NET_*` (URL/TOKEN/AGENT/ADVERTISE_HOST); state files `comms.db/.log/pid` -> `orbal-net.*`; help/usage strings; `smoke-tui.py` binary path.
- Crate metadata for crates.io: `license = "MIT OR Apache-2.0"`, `description`, `repository`, `readme = "README.md"`, `keywords`, `categories`; remove `publish = false`. Add `LICENSE-MIT`, `LICENSE-APACHE`, `README.md`.
- CI in the new repo (`.github/workflows/ci.yml`): fmt, clippy, test matrix, coverage, deny, build (ported from existing `comms.yml`), plus a `publish` job on `refs/tags/v*` running `cargo publish --token ${{ secrets.CARGO_REGISTRY_TOKEN }}` after tests pass. Keep GitHub-Releases binaries.
- Rewire `.botfiles`: remove `comms/` + `.github/workflows/comms.yml`; update `spawn.py` (env, state files, invoke installed `orbal-net`, bootstrap `cargo install`); docs/memory sweep (`AGENTS.md`, `.botfile/memory/tools/orchestration.md`, `sandbox.md`, `index.md`, `.claude/commands/spawn-team.md`).

## Non-goals
- No feature changes to the CLI/server/TUI - rename + packaging only.
- No change to the coordination protocol semantics, room model, or wire format (only env-var/binary NAMES change).
- Do NOT rebrand room/protocol structural names (`mission-*`, `squad-*`) or generic English "comms".
- No new dependencies, no CLI-framework migration (keep manual arg parsing).
- Do NOT make the `.botfiles` monorepo public; only the split-out crate is public.
- Do NOT rename the orchestration working artifacts under `orchestration/*.brief.md|*.roster.json` (planning docs, not product).

## Constraints
- Rust edition 2021, MSRV 1.78, `rust-toolchain.toml` pins 1.96.1 - keep CI aligned.
- Keep deps minimal (tiny_http, rusqlite, serde_json, ratatui, crossterm); `cargo deny check` must stay green (update license allowlist for MIT/Apache-2.0 if needed).
- crates.io first-publish is irreversible - real publish gated by the lead after `cargo publish --dry-run` + `cargo package --list` pass.
- The live orchestration runs on the CURRENT `comms` binary/env - do the `.botfiles` rewire last; never tear down the running mission server mid-flight.
- Repo creation, `CARGO_REGISTRY_TOKEN` secret, and any push token are human/authorized steps - request them, do not self-authorize.

## Acceptance criteria
- `zico-io/orbal-net` exists (public) with the crate + preserved history; `.botfiles` no longer contains `comms/`.
- New repo CI is green on push: fmt, clippy, test (ubuntu+macos), coverage, deny, build.
- `cargo publish --dry-run` succeeds; `cargo package --list` shows a clean, LICENSE-inclusive tarball.
- Tagging `v0.1.0` publishes `orbal-net 0.1.0` to crates.io via the pipeline (lead-gated).
- `cargo install orbal-net` yields a working `orbal-net` binary; `orbal-net --selfcheck` passes; `smoke-tui.py` passes against it.
- A fresh `spawn.py up` on a throwaway mission stands up rooms and coordinates agents using `orbal-net` + `ORBAL_NET_*` (validated before old path removal).
- No stray `comms`/`COMMS_*` product references remain in code or docs (grep clean, excluding structural/generic uses).

## Affected areas
- `.botfiles/comms/**` (moves to new repo): `Cargo.toml`, `src/main.rs`, `src/server.rs`, `src/tui/{mod,data,view}.rs`, `smoke-tui.py`, `deny.toml`, `rust-toolchain.toml`.
- New repo `zico-io/orbal-net`: `.github/workflows/ci.yml`, `LICENSE-MIT`, `LICENSE-APACHE`, `README.md`.
- `.botfiles`: `.github/workflows/comms.yml` (remove), `orchestration/spawn.py`, `AGENTS.md`, `.botfile/memory/tools/orchestration.md`, `.botfile/memory/tools/sandbox.md`, `.botfile/memory/index.md`, `.claude/commands/spawn-team.md`.

## Risks and unknowns
- Live substrate break: rename `.botfiles` last; keep the old binary until the new one is validated on a throwaway mission.
- Chicken/egg: `cargo install orbal-net` needs a published version - bootstrap from git/path until `v0.1.0` is on crates.io, then switch to the registry.
- Irreversible publish - dry-run + lead gate first.
- Human/authorized steps (repo, secrets) can block progress - surface early.
- `subtree split` history hygiene; `deny.toml` license allowlist.

## Team plan
- release-lead (claude/opus): owns the mission end-to-end; fixes the naming contract before workers diverge; sequences workstream A (new repo) before B (rewire); gates the irreversible crates.io publish; relays human-only steps (repo creation, secrets).
  - worker-cicd (claude/sonnet): stands up `zico-io/orbal-net` - subtree split with history, crate metadata + license + README, port CI + add publish job, `cargo publish --dry-run` verification.
  - worker-rebrand (claude/sonnet): rewires `.botfiles` - remove `comms/` + old workflow, update `spawn.py` (env/state/binary), sweep docs + memory, rename env vars consistently with the lead's contract.
