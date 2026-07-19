# Mission brief: eve-first-milestone

Long name: "~/dev/monkeys/apps/eve/ first milestone"

## Goal
Build the first milestone of the monkeys `agent` backend: the **P1 walking skeleton**
defined in `apps/agent/ARCHITECTURE.md`, plus enough of the `cli` cockpit to drive it
end to end from the terminal. Today `apps/agent` is proposal-stage - a tiny eve scaffold
(`agent.ts`, `instructions.md`, `channels/eve.ts`, `tools/propose_plan.ts`) and nothing
runs the mission loop. Success is a demoable vertical slice: a conductor opens the Ink
`cli`, briefs the assistant, watches it plan, approves the plan (which really pauses and
resumes the eve session), watches one squad lead edit a fixture repo in an eve sandbox
and stream typed progress, and reads the final report - all against `apps/agent` running
locally on port 4000. Note there is no literal `apps/eve/`; "eve" is the framework and
`apps/agent` is the eve project. This milestone turns the ARCHITECTURE proposal into the
first thing that actually walks.

## In scope
The P1 slice of `apps/agent` (the eve backend):
- **Mission loop skeleton.** Root assistant (the existing `agent.ts` + `instructions.md`)
  drives Brief -> Plan -> (one) Battle -> Report. Scout fan-out and parallel battles are
  P3 - one lead, one battle is enough to prove the loop.
- **HITL plan sign-off.** `propose_plan` / a `request_approval` tool that genuinely
  **pauses** the eve session via eve's human-in-the-loop primitive; the cockpit's
  approve / request-changes call **resumes** it. (Today `propose_plan` just echoes.)
- **One `lead` subagent that does real work.** A declared `subagents/lead/` that, on
  approval, runs in an **eve sandbox**, clones/opens a designated fixture repo, makes a
  real edit, runs a test, and **commits** - then stops. Opening a live GitHub PR is a
  non-goal (see below); the commit in the sandbox is the proof.
- **Typed event feed.** eve **hooks** emit the 8 progress kinds
  (`task-start/done/error/abort`, `step`, `phase`, `blocked`, `handoff`) plus
  `progress N/M` over the HTTP channel's SSE stream, scoped by mission/squad.
- **Report.** A step assembles a report (the diff / commit ref from the sandbox) and
  pauses for acceptance; the cockpit renders it.
- **Product layer (local Postgres).** A minimal Neon-shaped schema - `tenants`,
  `missions` (index row -> eve session id), `reports` - with `tenant_id` on every row
  from day one, and **bearer-token auth** on the channel that resolves a key to a tenant
  and scopes the session. Runs against a local/dev Postgres. No Vercel deploy, no
  Auth.js, no quotas, no Blob (those are P2).

The `cli` cockpit (the terminal surface), wired to the above:
- Drive the full loop from the terminal against `AGENT_URL` (default
  `http://localhost:4000`): **Chat** (brief the assistant, stream replies), **Plan**
  (render the proposed plan; approve / request-changes / sign off), **Progress/Fleet**
  (render the live SSE event feed), **Review** (render the mission report).
- Actions go over the agent HTTP API; observation is the read-only SSE stream. The
  cockpit holds no agent logic - it renders what `agent` emits.

## Non-goals
- **No live GitHub PR from the lead.** The lead edits + commits inside its sandbox and
  stops. No PR-opening from inside the sandbox (that needs the orchestrator bridge and is
  a later increment). The fixture repo is a scratch/throwaway target, not a real project.
- **No P2/P3 work.** No Auth.js sessions, no org/user/membership, no per-tenant quotas,
  no Vercel Blob, no RLS. No scout subagents, no parallel multi-battle fan-out, no
  local-vs-vercel executor flag, no AI-Gateway harness routing (claude/codex/pi).
- **No Vercel deploy.** Milestone runs locally (`eve dev` / `bun run dev`). Deploy,
  Marketplace Neon/Blob provisioning, and env passthrough for prod are deferred.
- **No `native` cockpit.** The GUI surface is untouched this milestone; only `cli`.
- **No changes to eve itself** or to the other monorepo apps (`web`, `docs`) beyond what
  the two touched apps require.
- No entity/memory-fact writing; the deliverable is product code, not curated memory.

## Constraints
- **Monorepo conventions are gates** (`monkeys/AGENTS.md`): Bun + Turbo, Biome
  (`bun run lint` / `format`), konsistent (`bun run konsistent`), `bun run check-types`,
  `bun test`. Any change touching a package needs a **changeset** or CI blocks the PR
  (release-less: `bunx changeset add --empty`). Conventional Commits (squash-merge gates
  the PR title). Never hand-edit `bun.lock` / `skills-lock.json`.
- **eve is a Vercel public beta** pinned at `eve@^0.22.5` (record the exact resolved
  version). Ground every eve claim - HITL pause/resume, sandbox, hooks, channel - in
  current eve docs (eve.dev/docs); design to concepts, not exact signatures. The PoC
  (`~/dev/eve-harness`, VERDICT: GO) already proved eve durable sessions + channels work;
  reuse that learning.
- **Node >= 24** for eve (the sandbox image / local toolchain must satisfy this even
  though the root `package.json` engines say >=18).
- **The HTTP + SSE contract is the load-bearing interface** between `agent` and `cli`.
  `agent`-side must pin it (routes, request/response shapes, SSE event envelope) early
  and post it into the mission room before `cli` diverges. Reuse the 8 event kinds the
  wider toolchain already defines; do not reinvent the envelope.
- **Local Postgres**, not hosted Neon, for the milestone (Neon-compatible driver against
  a local/dev database is fine); env-wire the connection string, do not commit secrets.
- No em dashes anywhere; use "-".
- **Ships to GitHub (`monkeys` repo).** Spawned agents have no `gh`/network and their
  clone origin is a local mirror, so the orchestrator bridges every live GitHub step
  (push + PR via `spawn.py bridge-pr eve-first-milestone`, settings). Agents *prepare*
  the branch/commits/PR text; the orchestrator executes. (Sandbox egress for `bun`
  install and AI-Gateway model calls is fine; only `gh`/origin-push is bridged.)

## Acceptance criteria
- `bun run dev` (or `eve dev --port 4000` in `apps/agent`) boots the agent; a `POST` to
  the HTTP channel starts an eve session and the assistant's replies stream back over SSE.
- The assistant proposes a plan and calls the approval tool, which **pauses** the session;
  a cockpit approve call **resumes** it and the mission proceeds. Request-changes loops
  back to a new plan. Verified end to end, not just unit-mocked.
- On approval, the `lead` subagent runs in an **eve sandbox**, edits the fixture repo,
  runs its test, and **commits** (a real commit ref exists); it does **not** open a PR.
- The SSE feed carries all 8 event kinds plus `progress N/M`, scoped by mission/squad,
  and the `cli` Fleet/Progress views render them live over one persistent connection.
- A report is assembled (diff / commit ref) and paused for acceptance; the `cli` Review
  view renders it.
- Postgres product layer exists: `tenants` / `missions` (-> eve session id) / `reports`
  with `tenant_id` on every row; bearer-token auth resolves a key to a tenant and scopes
  the session. Runs against local Postgres.
- The `cli` drives the whole loop (brief -> plan -> approve -> watch -> report) from the
  terminal against `AGENT_URL=http://localhost:4000`.
- All monorepo gates green for the touched packages: `check-types`, Biome lint,
  konsistent, `bun test`, and a changeset is present. `ARCHITECTURE.md` P1 status updated
  to reflect what shipped.

## Affected areas
- `apps/agent/` (the eve backend): `agent/agent.ts`, `agent/instructions.md`,
  `agent/channels/eve.ts` (bearer auth + SSE), `agent/tools/*` (approval, dispatch,
  report), new `agent/subagents/lead/`, new `agent/hooks/*` (event emission), a minimal
  `db/` product layer (schema + queries), `package.json`, `ARCHITECTURE.md` (status).
- `apps/cli/` (the cockpit): `src/app.tsx` + views (Chat, Plan, Progress/Fleet, Review),
  an agent-API/SSE client, `AGENT_URL` config, `package.json`.
- Repo root: `turbo.json` env passthrough (DB / gateway / sandbox tokens) if needed;
  a changeset under `.changeset/`.
- Read for grounding (do not modify beyond the two apps): `apps/agent/ARCHITECTURE.md`,
  `apps/agent/README.md`, `apps/cli/README.md`, `monkeys/AGENTS.md`, and the PoC at
  `~/dev/eve-harness` (VERDICT.md, `agent/`, `channels/`) for eve durable-session /
  channel patterns that already work.

## Risks and unknowns
- **eve beta surface.** HITL pause/resume, sandbox git operations, and hook event
  emission may not match the ARCHITECTURE's assumed shapes. Validate the pause/resume and
  the sandbox-commit mechanics against current eve docs and a tiny spike **before** the
  full loop is wired. The eve-harness PoC is the reference for what already works.
- **Sandbox doing a real git edit + commit under `eve dev` locally** - confirm the eve
  sandbox can clone/edit/commit a local fixture repo offline early; it gates the lead
  battle. Decide the fixture-repo source (a committed scratch repo vs one created on the
  fly).
- **The agent<->cli contract** is the sequencing risk: `cli` is blocked until the HTTP+SSE
  shape is fixed. Mitigate by having `agent`-lead publish the contract first; `cli` starts
  against that spec (or a stub) rather than waiting idle.
- **Local Postgres wiring** - which driver/connection, migrations vs a single schema
  file, and how `eve dev` gets the connection string. Keep it minimal (one schema, no
  migration framework) for the skeleton.
- **Node 24 vs monorepo `engines >=18`** - bump monorepo engine to 24
  image satisfy eve's Node requirement without breaking the other apps.
- **Changeset / konsistent friction** - eve projects are file-based (not Next.js);
  confirm konsistent rules and the changeset flow accept the two touched packages.

## Team plan
- repo: `/Users/percules/dev/monkeys`
- **agent-lead** (claude/opus): owns the `apps/agent` P1 backend end to end. Runs the
  early eve spike (HITL pause/resume + sandbox commit) to de-risk the beta, **pins the
  HTTP + SSE contract and posts it to the mission room before `cli` diverges**, owns the
  mission-loop wiring (assistant -> approval pause/resume -> one lead battle -> report),
  integrates both workers, keeps the monorepo gates green, updates `ARCHITECTURE.md`, and
  prepares the branch/commits/PR text for the orchestrator to bridge to GitHub.
  - **worker-runtime** (claude/sonnet): the eve agent core - the `request_approval` HITL
    tool (real pause/resume), the `subagents/lead/` that opens an eve sandbox, edits the
    fixture repo, runs a test and commits (no PR), the dispatch + report-assembly tools,
    and `instructions.md` updates. Owns the sandbox-commit proof.
  - **worker-platform** (claude/sonnet): the HTTP channel (bearer-token auth resolving
    key -> tenant, session scoping), the SSE event feed via eve **hooks** (all 8 kinds +
    `progress N/M`), and the local-Postgres product layer (`tenants` / `missions` ->
    session id / `reports`, `tenant_id` everywhere). Owns the API+SSE contract shape with
    the lead.
- **cli-lead** (claude/opus): owns wiring the `apps/cli` Ink cockpit to the agent. Builds
  against the pinned HTTP+SSE contract: the agent-API/SSE client, the Chat / Plan /
  Progress-Fleet / Review views, and `AGENT_URL` config, so a conductor drives the whole
  loop from the terminal. Verifies the end-to-end demo against a locally-running `agent`.
  - **worker-cli** (claude/sonnet): implements the cockpit views and the API/SSE client
    under the lead's direction - Chat (brief + streamed replies), Plan (approve /
    request-changes), Progress/Fleet (live event render over one SSE connection), Review
    (report), plus the co-located component tests.
