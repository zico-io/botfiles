# Handoff: scoping the eve-harness v0 mission

Audience: a fresh L1 orchestrator who will run `/scope-mission` for the first REAL
eve-harness increment (RFC S9 step 3), with no prior context. Read this cold, then
scope. This is a work artifact - no em dashes, use "-".

## 0. TL;DR

- We proved the thesis (orbal-net can be a native eve channel) with a throwaway PoC.
  Verdict: GO. Now build the real thing, smallest slice first.
- The RFC's next step (S9 step 3) is: convert ONE real leaf-worker role to an eve
  agent and run it in a live mixed fleet next to claude/codex/pi workers.
- Recommended v0 scope: do that as a LOCAL role (`eve start` in a herdr pane, sharing
  the LAN with orbal-net), NOT a deployed-to-Vercel role. Local sidesteps the two
  hardest open gaps (public reachability + git write-back from a Vercel Sandbox) while
  still proving the real claim: an eve worker is indistinguishable from a claude worker
  in the room. Deployed-remote is a later increment.
- Infra is already eve-ready (see section 4). You mostly need spawn.py wiring + a v0
  harness definition, not more infra prep.

## 1. The arc so far (where everything lives)

Three missions ran, in order:
1. `eve-harness` (RFC) - the north-star design. Committed to `.botfiles` main
   (`orchestration/eve-harness.rfc.md`, commit e46824f). This is the DESIGN OF RECORD.
   Sections 5, 6, 8, 9, 10 are the ones v0 leans on.
2. `orbal-net-push` - flipped orbal-net from poll/`wait` to server-push SSE (`recv`).
   Live now: agents block on `orbal-net recv <room>` (with `--since`/`--follow`), no
   poll loop. The RFC and PoC are written against this model.
3. `eve-harness-impl` (PoC) - built and proved the core mechanic. Deliverable is a
   standalone repo at `/Users/percules/dev/eve-harness` (LOCAL only, on `main`, not
   pushed to GitHub). Read these in that repo:
   - `VERDICT.md` - the go/no-go verdict + the three proofs + refinements. Read first.
   - `CONTRACT.md` - the full wire contract (orbal-net HTTP API, SSE frame shape,
     webhook frame, continuation-token mapping, ordering/exactly-once, outbound tools,
     env vars). v0 builds directly on this; sections 4 and 5 are load-bearing.
   - `HANDOFF.md` - the PoC's own handoff (bridge asks + precondition diffs).
   - `proofs/precondition-notes.md` - the infra gotchas (see section 4 caveat below).
   - `agent/` (eve project: channel + tools + instructions), `connector/` (the
     standalone connector), `harness/` (the repeatable proof runner), `test/`.
   - `docs/eve-harness.rfc.md` - a copy of the RFC, carried in-repo.

## 2. What is proven (do not re-litigate)

All three PoC proofs pass end to end (`node harness/run.ts --proofs=1,2,3` ->
OVERALL: PASS), on `eve@0.22.1` + Node 24 + orbal-net with `recv`/SSE:
- Proof 1 - SSE-frame -> turn: a room message, delivered by the connector as one
  `POST /orbal-net/message` frame, mints a durable eve turn keyed by the
  `orbal-net:<room>:<agent>` continuation token; the agent's `orbal_net_send`/`_event`
  land back in the room. Exactly the RFC S5 sketch.
- Proof 2 - durability: a codeword survived a hard restart on the same durable session,
  AND a genuine cross-network Vercel redeploy (real new build) resumed the same session
  and recalled it. Vercel Workflows DO resume across a new build - the property the
  RFC's remote story needs.
- Proof 3 - connector-restart resume: connector killed mid-conversation resumed from
  its persisted `<msgSeq>:<evtSeq>` cursor via `--since`, zero lost/dup, in two
  kill-window scenarios.

## 3. What v0 MUST carry forward (findings the PoC surfaced)

These are the load-bearing details a cold v0 team would otherwise re-discover the hard
way. All are documented in `VERDICT.md`/`CONTRACT.md`; the essentials:

Design refinements (RFC-level, must be in the v0 design):
1. A DEPLOYED agent's outbound tools cannot reach a private-LAN orbal-net (empirically
   confirmed, hard timeout). Resolution is one of: (a) orbal-net reachable at a
   public/VPN address, or (b) the connector bridges BOTH directions (proxies outbound
   tool calls too, not just inbound frames). A LOCAL role sidesteps this entirely (it
   shares the LAN with orbal-net) - the main reason to do v0 local-first.
2. The agent's orbal-net identity must be a room member and must know which room:
   orbal-net rejects `/send` from a non-member (403). The PoC's connector `/join`s the
   room as the agent on startup, and the channel injects `orbal-net-room: <room>` into
   the turn context so the agent replies to the right room. Both belong in the real
   connector/channel.

Mechanics (must hold in any real connector):
3. eve does NOT durably queue concurrent deliveries to one continuation token. The
   connector therefore MUST serialize strictly per (room, agent): deliver one frame,
   wait for the session to park (`session.waiting`), commit its cursor, then read the
   next frame. This serialization is what makes zero-lost/zero-dup hold.
4. Exactly-once = connector's park-gated, fsync'd cursor commit (durable authority) +
   the channel's in-memory msgSeq dedup guard (cheap extra layer).
5. Resume choreography: let a turn fully checkpoint before any kill; after a cold
   restart the session needs a beat to rehydrate (re-deliver if a frame lands too
   early); locally, `eve start` (built production server, port 3000) resumes durable
   sessions but `eve dev` (port 2000) does NOT - do not conflate them; wipe
   `.workflow-data` per local run (a real deployment gets a fresh store per deploy).

## 4. Infra already in place (you likely do NOT need more prep)

The sandbox image (`botfiles-agent`) and `spawn.py` are now eve-ready, committed to
`.botfiles` main (`94788f6`, `ac52f1b`). Verified in the rebuilt image:
- `orbal-net` binary has `recv`/SSE (git-installed from main; not yet on crates.io).
- `vercel` CLI baked (npm global).
- Node 24 baked (NodeSource `setup_24.x`) - eve requires `>=24`. NOTE: this SUPERSEDES
  `proofs/precondition-notes.md` section 1 (the Node-24 in-VM symlink workaround) -
  that workaround is obsolete, Node 24 is now the image default.
- Vercel credential proxy: `mission_secrets()` copies the host `vercel login` cred into
  `/secrets/vercel.auth.json`; the entrypoint places it at the guest
  `~/.local/share/com.vercel.cli/auth.json`. Verified: in-VM `vercel whoami` -> `zico-io`.
  KEEP this provisioning for any eve/Vercel role or deploys break. Documented in
  `.botfile/memory/tools/sandbox.md`.

Operational facts for any Vercel-linked role (from `precondition-notes.md` section 2):
- `npx eve link` needs a TTY and refuses non-interactive. The working substitute is
  `vercel link --yes --scope <team-slug> --project <name>`, which links the project AND
  writes `.env.local` with a fresh `VERCEL_OIDC_TOKEN`.
- AI Gateway model calls then resolve automatically via that OIDC token - no separate
  Gateway key setup. (`<team-slug>` has no non-interactive default; `vercel link --yes`
  without `--scope` fails but lists valid slugs in its JSON error `choices[]`.)
- The host is logged into Vercel as team `zico-io`.

## 5. Recommended v0 scope (the decision to tee up in scoping)

Per RFC S9 step 3: convert exactly ONE leaf-worker role to eve, run it side by side
with claude/codex/pi workers in the same `squad-<lead>` room. Success = `orbal-net tui`
/ `peek` cannot tell the eve worker apart from a claude worker in the room thread or the
progress panel.

The pivotal fork to settle with the human during scoping - LOCAL vs DEPLOYED:
- LOCAL (recommended for v0): the eve worker runs as `eve start` in its own herdr pane
  inside the mission VM, connector alongside it, orbal-net on the LAN. Sidesteps BOTH
  the reachability refinement (#1 above) and the git write-back gap (section 6). It
  shares the mission clone at `/work` exactly like a claude worker, so `wcommit`/harvest
  just work. This is the true minimal v0 and still proves the real claim.
- DEPLOYED (defer): the eve worker runs as a Vercel deployment. Forces solving public
  orbal-net reachability AND git write-back from a Vercel Sandbox before it can be a
  fleet member. That is RFC S9 step 4+, not v0.

Suggested slug for the mission: `eve-harness-v0`.

## 6. Open decisions / risks for v0 scoping

- git write-back gap (RFC S10 risk 1): a DEPLOYED eve agent's sandbox is a Vercel
  Sandbox microVM, not the shared host-mounted mission clone that `wcommit`/harvest use.
  Unsolved. A LOCAL v0 role moots this (it is in the mission clone). Do not convert a
  deployed role until this is designed.
- spawn.py changes for a LOCAL eve role (RFC S8, scoped down): a launch path that runs
  `eve start` in a pane (not the generic `HARNESSES` shell-command shape), plus a
  connector lifecycle (an `orbal_net_connector_up(feature)` symmetric to
  `orbal_net_up()`, detached, pid in `mission.json`, killed by `down`, reported by
  `status`). `bootstrap()` is NOT needed for an eve role (the join/recv/emit protocol is
  compiled into the channel + tools, not re-taught by prompt). `poke` still applies to a
  local pane. `validate()`'s 3-layer/room rules are untouched.
- The connector is a new always-on dependency whose failure is SILENT (rooms keep
  working, the eve agent just stops receiving). It must be crash-restart-safe (it is, in
  the PoC) and `status` must surface its liveness.
- Keep the eve role a FIRST-CLASS orbal-net agent (its own identity/room membership/
  cursor), never an eve subagent - subagents have no identity/room/cursor and would
  break `peek`/`events`/tui monitoring (RFC S7).
- Reuse, do not reinvent: the PoC's `agent/channels/orbal-net.ts`, `agent/tools/
  orbal_net_*.ts`, and `connector/` are working reference implementations built to
  `CONTRACT.md`. v0 should harden and productionize these, not start from scratch.

## 7. Next action for the incoming orchestrator

Run `/scope-mission eve-harness-v0 convert one leaf-worker role to a local eve agent per
the eve-harness RFC S9 step 3` (or your own phrasing). During the interview, settle the
LOCAL-vs-DEPLOYED fork (section 5) first - it determines nearly everything else. Point
the scoping at the RFC (`orchestration/eve-harness.rfc.md`) and the PoC deliverable
(`/Users/percules/dev/eve-harness`, especially `VERDICT.md` + `CONTRACT.md`) as the
grounding sources, and drop the RFC + relevant PoC docs into the mission clone the way
the PoC mission had its RFC dropped in (the eve-harness repo is a separate repo from the
mission's target repo, so its docs will not be in the clone by default).
