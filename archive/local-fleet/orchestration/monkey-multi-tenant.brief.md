# Mission brief: monkey-multi-tenant

Long name: "apps/monkey P2 - multi-tenant (org/user/membership + API-key lifecycle + soft quotas + Auth.js onboarding + hosted Neon + deploy)"

## Goal
Build the P2 multi-tenant increment of the monkeys `agent`/`monkey` backend on top of the
P1 walking skeleton (PR #11). P1 shipped a single seeded `dev` tenant with bearer-key auth
and `tenant_id` on every row; P2 turns that into a real multi-tenant product: an
org/user/membership model, a full API-key lifecycle (issue/list/revoke), soft per-tenant
usage tracking, and human onboarding via Auth.js in `apps/web` - all persisted in a hosted
Neon Postgres and deployed to Vercel. Success is a demoable multi-tenant slice: a human
signs up (Auth.js) which creates their org, they mint an API key from a minimal web page,
and a cockpit uses that key to run a mission against the deployed `monkey` with every row
tenant-scoped and per-tenant usage recorded - with two tenants provably isolated from each
other. This is the increment that makes `monkey` safe for more than one user.

## In scope
Backend - `apps/monkey` (the eve backend):
- **Org/user/membership model.** Extend `agent/db/schema.sql` with `users` and
  `memberships` (tenant_id, user_id, role) alongside the existing `tenants`/`api_keys`/
  `missions`/`reports`. A user belongs to one or more tenants via a membership; the P1
  `requireTenantCaller` (already expects a `user` principal with `tenantId` + `userId`)
  resolves against real membership, not the seeded dev shortcut.
- **API-key lifecycle.** Endpoints to issue (returns the raw key ONCE, stores only the
  sha256 hash - matching P1's `key_hash`), list (metadata only: label, created_at,
  last_used_at, revoked_at - never the raw key), and revoke a tenant's keys. Add the
  lifecycle columns to `api_keys`. All tenant-scoped and requiring an authenticated
  principal.
- **Auth for management routes.** The custom eve `AuthFn` (P1 resolves bearer key ->
  tenant) is extended so a human acting from `apps/web` (an Auth.js session) can call the
  key/member-management routes as a `user` principal for their tenant. Bearer-key auth for
  cockpit/session routes stays exactly as P1 pinned it.
- **Soft usage tracking (no enforcement).** Record per-tenant usage - at minimum active
  sandbox executions and missions - and expose a read endpoint. Do NOT block or 429 on
  over-use; just count and surface. Enforcement is a later pass.
- **Tenant isolation hardening.** Query-scoping by `tenant_id` on every row (as P1); a
  cross-tenant read stays `404` (do not leak existence). Postgres RLS remains deferred.

Onboarding - `apps/web` (Next.js), Auth.js only:
- **Auth.js (NextAuth) session/login/signup** with a Postgres adapter against the same
  Neon DB. On first signup a user gets an org (tenant) + owner membership.
- **A minimal API-key page**: issue / list / revoke the logged-in user's tenant keys. NO
  full admin console, no operator dashboard, no marketing pages - just enough UI to prove
  the onboarding -> key -> cockpit flow.

Persistence + deploy (orchestrator-bridged - see Constraints):
- **Hosted Neon Postgres** provisioned (not local); `DATABASE_URL` wired into both apps.
- **Deploy `monkey` (eve) and `web` (Next.js) to Vercel** as their own projects; the
  multi-tenant demo runs against the deployed URLs, not just `eve dev`.

## Non-goals
- **No quota ENFORCEMENT.** Usage is tracked and surfaced only; no hard limits, no 429s,
  no billing. (Enforcement + billing are a later increment.)
- **No full admin/operator console** and **no marketing site** in `apps/web` - only
  Auth.js + the minimal key page. `native` cockpit untouched.
- **No P3 workforce** (scouts, parallel battles, change-request loop, executor flag,
  harness routing) - P2 is tenancy + onboarding + deploy only.
- **No Postgres RLS** - isolation stays query-scoping by `tenant_id`.
- **No change to the P1 cockpit/session contract** (`API_CONTRACT.md` session + fleet +
  report routes) beyond additive management routes; the cli keeps working unchanged.
- **No rewrite of P1's bearer-key session auth** - P2 is additive.
- No entity/memory-fact writing; the deliverable is product code.

## Constraints
- **Builds on PR #11 / branch `mission-eve-first-milestone`.** Branch this mission from
  that work (the P1 db/auth/channel layer is the foundation; do not regress it). Reuse
  `agent/db/schema.sql`, `lib/tenant.ts`, `channels/eve.ts` AuthFn, `API_CONTRACT.md`.
- **Monorepo conventions are gates** (`monkeys/AGENTS.md`): Bun + Turbo, Biome, konsistent,
  `check-types`, `bun test`. Any package change needs a **changeset** or CI blocks the PR.
  Conventional Commits. Never hand-edit `bun.lock` / `skills-lock.json`.
- **eve@0.22.5 pinned** (as P1); Auth.js/NextAuth current stable in `apps/web` (Next.js).
  Ground eve-side auth claims in the bundled eve docs (`multi-tenant-auth.md`).
- **Shared schema ownership + user-identity SSOT.** `apps/monkey/agent/db/schema.sql` is
  the SSOT for the product tables (tenants/users/memberships/api_keys/missions/reports/
  usage). The product `users` table is the ONE source of user identity - Auth.js's adapter
  maps onto it (adapter tables reference/reconcile to the product `users` row), never a
  second divergent user record. `monkey`-lead pins how `web` reaches the data (shared Neon
  direct vs monkey management endpoints) and posts it before `web` diverges.
- **Hosted Neon + Vercel deploy are orchestrator-bridged.** Spawned agents have no
  `gh`/network-to-GitHub and their clone origin is a local mirror. The orchestrator:
  provisions Neon, sets `DATABASE_URL` + `AUTH_SECRET` + AI-Gateway/OIDC + sandbox creds as
  Vercel env, runs the live `vercel deploy` for both projects, and opens the PR
  (`spawn.py bridge-pr monkey-multi-tenant`). Agents PREPARE deploy config (`vercel.json`,
  env manifests, the schema-apply step) and the schema/Auth.js code as files/text; the
  orchestrator executes anything touching live Neon/Vercel/GitHub. (In-VM `vercel deploy`
  may work with the proxied Vercel cred, as proven in P1 - the orchestrator keeps that cred
  fresh; treat the deploy as a bridged step regardless.)
- No em dashes anywhere; use "-". Do not commit secrets (`DATABASE_URL`, `AUTH_SECRET`).

## Acceptance criteria
- Schema extended: `users`, `memberships`, `api_keys` lifecycle columns, and a usage
  table/counters - applied to hosted Neon via the documented `psql -f schema.sql` step.
- API-key lifecycle works end to end: issue returns a raw key exactly once and stores only
  its hash; list shows metadata (never the raw key); revoke invalidates it (a revoked key
  -> 401). All tenant-scoped.
- A human can sign up via Auth.js in `apps/web`, which creates their org + owner
  membership, log in, and issue/list/revoke their tenant's API keys from the minimal page.
- A cockpit (the P1 cli, unchanged) runs a full mission against the DEPLOYED `monkey`
  using a web-issued key; every mission/report row is tenant-scoped; per-tenant usage
  (sandbox executions, missions) is recorded and readable.
- **Two-tenant isolation proven:** tenant A cannot read tenant B's missions/reports/keys
  (cross-tenant -> 404), demonstrated with a test/script.
- Both apps deploy to Vercel and the demo runs against the deployed URLs; `DATABASE_URL`
  points at hosted Neon.
- All monorepo gates green for touched packages (`check-types`, Biome, konsistent,
  `bun test`), changesets present. `ARCHITECTURE.md` P2 status updated. New/changed routes
  reflected in `API_CONTRACT.md`.

## Affected areas
- `apps/monkey/agent/db/schema.sql` (users/memberships/api-key lifecycle/usage),
  `db/queries.ts`, `lib/tenant.ts` (membership resolution), `channels/eve.ts` +
  `channels/monkey.ts` (Auth.js-session AuthFn + management routes + usage read),
  `API_CONTRACT.md`, `ARCHITECTURE.md` (P2 status).
- `apps/web/` (Next.js): Auth.js setup + Postgres adapter, login/signup, org-on-signup,
  the minimal API-key page, an API/DB client to the shared Neon or monkey endpoints,
  `package.json` (Auth.js deps + changeset).
- Deploy config (agent-prepared, orchestrator-applied): `vercel.json`/project settings for
  both apps, env manifests (`DATABASE_URL`, `AUTH_SECRET`, AI-Gateway/OIDC, sandbox creds),
  the Neon schema-apply step. Repo root `turbo.json` env passthrough; `.changeset/`.
- Read for grounding (do not regress): PR #11 / branch `mission-eve-first-milestone`
  (`apps/monkey/agent/db/*`, `lib/tenant.ts`, `channels/*`, `API_CONTRACT.md`),
  `apps/monkey/ARCHITECTURE.md` (Multi-tenancy section), `monkeys/AGENTS.md`.

## Risks and unknowns
- **eve AuthFn accepting an Auth.js session** (a human principal) alongside bearer keys is
  the crux and the least-proven part. Validate early how `apps/web` authenticates to
  `monkey` (shared-Neon-direct vs monkey management endpoints vs a session-token AuthFn
  branch) - pin it before `web` builds against it.
- **Auth.js adapter mapped onto the product `users` SSOT** - the product `users` table is
  the decided source of user identity (see Constraints); the Auth.js adapter must reference
  it rather than create a parallel user record. The footgun is a divergent Auth.js user
  table - avoid it. Test that signup creates exactly one product user + one org + one
  membership.
- **Hosted Neon + deploy** adds real ops: Neon provisioning, applying `schema.sql` to a
  remote DB, Vercel env wiring (`DATABASE_URL`/`AUTH_SECRET`/OIDC/sandbox creds), and two
  Vercel projects. This is orchestrator-bridged but the deploy interplay (OIDC for AI
  Gateway + Vercel Sandbox executor from the deployed Function) needs a live check, like
  P1 - confirm the deployed `monkey` can still reach the model + sandbox.
- **Deploying eve to Vercel (not just `eve dev`)** may surface build/runtime differences
  from local; the globalThis-shared fleet bus is single-process only (P1 P2-note) - a
  multi-instance deploy could split the bus. Confirm the demo path stays single-instance or
  document the limit.
- **Secret hygiene** - `DATABASE_URL`/`AUTH_SECRET` must live in Vercel env + local
  `.env.local` (gitignored), never committed; the schema seed must not create non-dev keys.
- **Branch base** - starting from an unmerged PR #11 branch; if #11 changes in review, this
  mission must rebase. Coordinate the base with the orchestrator.

## Team plan
- repo: `/Users/percules/dev/monkeys` (branch from `mission-eve-first-milestone` / PR #11)
- **monkey-lead** (claude/opus): owns the `apps/monkey` P2 backend end to end. Pins how
  `web` reaches the data + the Auth.js-session auth mechanism and posts it to the mission
  room before `web` diverges (same contract-first discipline as P1). Owns the schema
  extension, membership resolution, the additive management routes, and the
  `API_CONTRACT.md`/`ARCHITECTURE.md` updates; integrates both workers; keeps gates green;
  prepares the Neon/Vercel deploy config + schema-apply step as files/text for the
  orchestrator to execute, and the branch/PR text to bridge.
  - **worker-tenancy** (claude/sonnet): the org/user/membership model - schema
    (`users`/`memberships`, `api_keys` lifecycle columns, usage table), `db/queries.ts`,
    `lib/tenant.ts` membership resolution, and the API-key issue/list/revoke endpoints
    (hash-on-store, raw-once, revoke->401). Owns the two-tenant isolation test.
  - **worker-auth-quota** (claude/sonnet): the eve `AuthFn` extension accepting an Auth.js
    session principal for management routes (keeping P1 bearer-key auth intact), the soft
    usage tracking (record sandbox executions + missions per tenant) + read endpoint, and
    tenant-scoping hardening. Owns the deployed-monkey model+sandbox live re-check.
- **web-lead** (claude/opus): owns `apps/web` Auth.js onboarding. Builds against
  monkey-lead's pinned data/auth contract: Auth.js (NextAuth) + Postgres adapter,
  login/signup, org-on-signup + owner membership, and the minimal issue/list/revoke API-key
  page. Maps the Auth.js adapter onto the product `users` SSOT (no parallel user record).
  Verifies the signup -> key -> cockpit demo against the deployed backend.
  - **worker-web** (claude/sonnet): implements the Next.js pieces under the lead - Auth.js
    config + adapter, the login/signup + key-management page and its data client, and
    co-located tests; prepares the `apps/web` Vercel deploy/env config as text.
