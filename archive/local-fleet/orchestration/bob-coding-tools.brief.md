# Mission brief: bob-coding-tools

Long name: "enhance our bob harness with coding agent tools"

## Goal
bob is our production eve harness: a durable backend agent that sits in an
orbal-net room as a peer to claude/codex/pi workers. v0 is proven, but its agent
has only three coordination tools (`orbal_net_send`, `orbal_net_event`,
`orbal_net_progress`) - it can talk and emit progress, but it cannot read, edit,
or commit code. So it coordinates like a peer but cannot actually *do the work*
like one.

This mission closes that gap: give bob's eve agent real coding tools so it
produces commits indistinguishable from its claude/codex/pi peers. Success = a
bob worker, dropped into a live mixed fleet on a shared clone, edits files, runs
commands, and lands serialized commits on the same branch as its peers - with no
special-casing by the orchestrator.

## In scope
- Typed eve tools, written fresh in `/Users/percules/dev/bob`, following the
  existing `agent/tools/orbal_net_*.ts` pattern (Zod schema + handler):
  - **File**: read, write, edit (agent-friendly typed file ops).
  - **Code search**: ripgrep-backed search and fd-style file find (modern,
    agent-friendly, structured output - not raw grep).
  - **Git**: status, diff, log, and a commit tool that goes through the
    fleet's `wcommit` serialization (see Coordination below).
  - **Bash**: a general shell-execution tool so the agent can run builds,
    tests, and lints to verify its own work (the escape hatch that gives full
    peer parity).
- Wire the tools into the agent: register them in the agent config and teach
  their use in `agent/instructions.md`.
- Update the contract/docs: `docs/PRODUCTION-CONTRACT.md`, `README.md`, and any
  bootstrap prompt text, so the new tool surface is the documented SSOT.
- Prove it: run bob in a live mixed fleet on a shared clone and demonstrate it
  landing real serialized commits alongside claude/codex/pi peers.

## Non-goals
- Vercel deployment. This mission targets local run only (`eve start` in a herdr
  pane, the way `spawn.py` launches it today). Tools should not *preclude* a
  future deploy, but deploy-specific sandbox semantics are out of scope.
- Per-agent isolated sandboxes. We keep the shared-clone + `wcommit` model that
  the current fleet uses; a new coordination model is out of scope.
- Reworking the connector, the webhook channel, or the orbal-net wire contract.
  This mission adds tools; it does not touch frame delivery.
- New orchestration harnesses or changes to how `spawn.py` places/launches eve
  beyond what the new tools require (e.g. ensuring ripgrep/fd are available).

## Constraints
- Stack: TypeScript on eve (pinned `eve@0.22.1`), Node 24+, AI SDK 7, Zod. Match
  the existing tool file conventions exactly; do not bump the eve pin.
- Shared clone: the fleet works on one clone at `/work`. Commits are serialized
  across agents by the host-side `wcommit` script (see `spawn.py`). The git
  commit tool must route through that same serialization, not `git commit`
  directly, or it will race its peers.
- Local dependencies: ripgrep (`rg`) and fd must be available on the host where
  eve runs. If they are not baked in, provisioning is part of the mission
  (coordinate with the orchestrator - `provision.sh` / sandbox image is the
  orchestrator's to change).
- Bash tool is a real capability: scope its working directory to the clone and
  keep it auditable, but it is intentionally a full shell.
- GitHub: spawned agents have no `gh`/network and their clone's origin is a local
  mirror, so the orchestrator bridges all live GitHub steps (push + PR via
  `spawn.py bridge-pr bob-coding-tools`, release edits, repo settings) - agents
  *prepare* those artifacts as files/text for the orchestrator to execute.

## Acceptance criteria
- All four tool groups (file, search, git, bash) exist as typed eve tools with
  Zod schemas, registered on the agent, and documented in `instructions.md`.
- A bob worker in a live mixed fleet edits files and lands at least one
  serialized commit on the shared branch via the wcommit path, interleaved with
  peer commits, with no lost/duplicated/corrupted commits.
- The agent can run the repo's build/test command via the bash tool and act on
  the result (verify-before-commit demonstrated at least once).
- `PRODUCTION-CONTRACT.md` and `README.md` reflect the new tool surface as SSOT.
- `npx eve build` succeeds; existing proofs (e.g. connector-restart) still pass.

## Affected areas
- `/Users/percules/dev/bob/agent/tools/` - new tool files (file, search, git, bash).
- `/Users/percules/dev/bob/agent/` - agent config (tool registration) and
  `instructions.md`.
- `/Users/percules/dev/bob/docs/PRODUCTION-CONTRACT.md`, `/Users/percules/dev/bob/README.md`.
- `/Users/percules/dev/bob/package.json` - only if a new dep is truly needed;
  prefer eve's built-in sandbox primitives + `rg`/`fd` shell-outs first.
- Orchestrator (owned by orchestrator, not the fleet):
  `/Users/percules/.botfiles/orchestration/spawn.py` and provisioning, if the
  wcommit tool contract or ripgrep/fd availability need adjustment.

## Risks and unknowns
- **wcommit coupling.** `wcommit` is a host-side script the classic harnesses
  shell out to. The eve agent must reach the same serialization. Open question:
  does the eve tool shell out to the same `wcommit` binary/script, or replicate
  its locking? Reproduce the current commit flow before designing the tool.
- **Bash + shared clone.** A full shell on a shared clone can stomp peers
  (stray `git` state, uncommitted churn). Scope cwd and be careful the bash tool
  does not bypass wcommit for commits.
- **ripgrep/fd availability.** Local run depends on `rg`/`fd` on the host;
  confirm before assuming, provision if missing.
- **Verify-before-commit UX.** Teaching the model to run tests then commit is a
  prompt/instructions problem as much as a tools problem; budget instructions
  iteration.

## Team plan
- repo: `/Users/percules/dev/bob`
- **lead-bob** (claude/opus): owns tool architecture and the wcommit contract,
  agent wiring (tool registration + `instructions.md`), all docs
  (PRODUCTION-CONTRACT, README, bootstrap), and the live-fleet proof. Integrates
  the two workers' tools and coordinates with the orchestrator on any spawn.py /
  provisioning needs.
  - **worker-tools-fs** (claude/sonnet): builds the file tools (read/write/edit),
    the ripgrep/fd code-search tools, and the bash execution tool. Owns the
    generic filesystem/exec surface.
  - **worker-tools-git** (claude/sonnet): builds the git tools (status, diff,
    log) and the wcommit-serialized commit tool. Owns everything that touches
    version control and the shared-clone serialization.
