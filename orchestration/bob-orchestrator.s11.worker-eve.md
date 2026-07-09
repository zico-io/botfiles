<!--
worker-eve draft for orchestration/bob-orchestrator.rfc.md, Section 11 (Appendix).
rfc-lead: worker-orch's connector/membership/bridge risks are NOT yet merged into
11.1 below - placeholder marked where they slot in. Sources in 11.2 are deduped
across worker-eve's sections (3,4,7), worker-orch's sections (5,6,8), and the
parent eve-harness RFC's own appendix; merge worker-orch's own citations in too
if any fell outside what's listed here.
-->

## 11. Appendix

### 11.1 Beta-risk register

eve and AI SDK 7 are both beta or newly-shipped; this register follows the same format as
`eve-harness.rfc.md` S11.1 - for each primitive this RFC leans on, the churn risk and the
hedge that keeps a breaking change small. Entries below are new to bob-as-L1 or sharpen an
entry the parent RFC already made; they do not repeat parent-RFC entries (durable
sessions/Workflows event-count and payload-size limits, the AI Gateway/OIDC auth
dependency, the channel HTTP contract, the subagent delegation contract) which still apply
unchanged and are not restated here.

- **`@ai-sdk/tui` as a durable-session client (section 4, the single highest-risk item in
  this RFC).** No fetched doc - not `ai-sdk.dev`'s terminal-ui page, not the parent RFC's
  own S3.3/S6.4 citations - documents a supported way to back `runAgentTUI` with a durable,
  `continuationToken`-addressed, `WorkflowAgent`-style session rather than an in-process
  `ToolLoopAgent`. Section 4's position (a thin client driving the TUI's render primitives
  against eve's session/stream HTTP API instead of calling `runAgentTUI({ agent })`
  unmodified) is this RFC's best current answer, not a documented feature. Hedge: prototype
  this specific wiring - render primitives fed by `GET /eve/v1/session/<id>/stream`, input
  fed by `POST /eve/v1/session` with a fixed `continuationToken` - as the very first build
  step (ahead of anything else in this RFC's eventual migration path), before any other
  part of bob's interactive design is treated as settled. If `@ai-sdk/tui`'s internals turn
  out not to be reusable outside its own entry point, the fallback is a hand-built terminal
  renderer against the same session/stream API (losing the package's rendering code, not
  the architecture), not a redesign of section 4's session model itself - the durable
  session is the load-bearing part, the TUI package is a convenience layer on top of it.
- **Skills: `load_skill` auto-dispatch and Agent-Skills-standard portability (section 7).**
  Two separate claims, two separate risks. (a) The model-driven `load_skill` dispatch
  (description matching or explicit naming triggers the load) is described only in prose in
  the fetched docs, with no versioned contract cited - a future eve release could change
  matching behavior (e.g. stricter/fuzzier description matching) without changing the
  `SKILL.md` file format itself. Hedge: keep skill descriptions unambiguous and keep the
  slash-command-style explicit-naming path (section 7's position that bob's own
  instructions.md names the two ported skills outright) as the primary invocation path, so
  the port does not depend on matching behavior staying exactly as documented today. (b)
  "Skills authored against the Agent Skills standard port as-is" [eve-docs: skills] is a
  portability claim taken from prose, not verified against an actual port in this RFC (no
  code was written, per the non-goals). Hedge: treat the `.claude/commands/*.md` ->
  `SKILL.md` port in section 7 as a fast, cheap spike to run early and literally, before
  the rest of bob's skill-dependent workflow (scope-mission, spawn-team) is assumed to work
  unmodified.
- **Schedules: dev-vs-prod firing semantics (section 3.3).** `eve dev` never fires a
  schedule on its cron cadence at all - only a manual one-shot dispatch route
  [eve-docs: schedules] - which means any schedule-based capability bob might gain later
  (section 3.3 names this as a candidate, not a design) is untestable end to end without
  running the full production `eve start` path, the same server bob's interactive session
  already depends on. Hedge: this is actually a *low* risk for THIS RFC specifically, since
  bob already commits to running `eve start` for the human-facing session (section 4) - the
  dev/prod schedule gap only bites a workflow that tries to develop and test a schedule
  under `eve dev` and expect production firing behavior, which this RFC does not propose
  doing.
- **Session cardinality at bob's multiplicity (sections 4, 5, 8 collectively).** The parent
  RFC's register does not address concurrent-session *count* at all, only per-session
  limits. bob-at-L1 is the first role in this fleet whose normal operation is N+1
  simultaneous durable sessions on one agent identity (one human-facing, one per actively
  driven mission - worker-orch's S5/S8), not the fixed one-or-two the parent RFC's lead/
  worker mapping assumed. No fetched doc gives a ceiling on concurrent sessions per eve
  agent. Hedge: treat "however many missions a human plausibly runs at once" as an
  assumption to validate empirically at the first real multi-mission demo, not a verified
  property; if a ceiling is hit in practice, the degradation path is bounding how many
  missions bob actively drives at once, not a redesign of the per-mission-session model.

**[worker-orch's risks - connector incremental attach/detach, cross-session notify
concurrency, GitHub-bridge approval-config mechanism, herdr-tool minimalism - are drafted
in `orchestration/bob-orchestrator.worker-orch-sections.md`'s "Ranked items for section 10"
and are NOT duplicated here; rfc-lead is merging the register with those risks in section
10's ranked list. Ordering across the merged 10/11 material is rfc-lead's call.]**

### 11.2 Sources

eve and AI SDK, primitives this RFC cites beyond what `eve-harness.rfc.md` S11.2 already
lists:
- [eve-docs: skills] https://eve.dev/docs/skills
- [eve-docs: schedules] https://eve.dev/docs/schedules
- [eve-kb: add-skills] https://vercel.com/kb/guide/how-to-add-eve-skills
- [ai-sdk-docs: terminal-ui] https://ai-sdk.dev/docs/agents/terminal-ui

Carried forward unchanged from `eve-harness.rfc.md` S11.2 (consumed as proven givens per
this RFC's scope, not re-fetched):
- [eve-docs: overview] https://vercel.com/docs/eve
- [eve-docs: concepts] https://vercel.com/docs/eve/concepts (re-fetched fresh by both
  worker-eve and worker-orch during this mission to confirm current wording; unchanged from
  the parent RFC's citation)
- [eve-docs: channels-overview] https://eve.dev/docs/channels/overview
- [eve-docs: channels-custom] https://eve.dev/docs/channels/custom
- [eve-docs: subagents] https://eve.dev/docs/subagents
- [eve-kb: subagents] https://vercel.com/kb/guide/how-to-use-eve-subagents
- [eve-docs: pricing] https://vercel.com/docs/eve/pricing
- [eve-blog: introducing-eve] https://vercel.com/blog/introducing-eve
- [eve-github: readme] https://github.com/vercel/eve/blob/main/README.md
- [fluid-compute-docs: default-settings-by-plan] https://vercel.com/docs/fluid-compute
- [ai-sdk-blog: ai-sdk-7] https://vercel.com/blog/ai-sdk-7

Our stack (this repo and its mission artifacts):
- [spawn.py] orchestration/spawn.py
- [orchestration.md] .botfile/memory/tools/orchestration.md
- [AGENTS.md orchestration protocol] AGENTS.md
- [eve-harness.rfc.md] orchestration/eve-harness.rfc.md - the design of record this RFC is
  a sequel to; sections 3, 5, 6, 7, 8, 9, 10 consumed as proven givens throughout.
- [eve-harness-v0.handoff.md] orchestration/eve-harness-v0.handoff.md - the leaf-worker v0
  scoping handoff; sections 2 and 3's proven facts (continuation-token session keying,
  connector serialization, `eve start` vs `eve dev` resume behavior) are load-bearing for
  sections 4 and 5 of this RFC.
- [eve-harness-v0.brief.md] orchestration/eve-harness-v0.brief.md - the leaf-worker v0
  mission brief; its Constraints section is the source for the "eve does not durably queue
  concurrent deliveries to one continuation token" fact this RFC's section 4.4 and
  worker-orch's section 5 both depend on.
- [bob-demo.evidence.md] orchestration/bob-demo.evidence.md - the live-fleet proof that an
  eve leaf worker is indistinguishable from a claude worker in the room thread and progress
  panel; cited by section 8's coexistence argument for converting L1 without touching L2/L3.

Beta note (unchanged from the parent RFC): eve is a Vercel public beta and AI SDK 7's
terminal-UI package is newly shipped; framework, APIs, and behavior may change before GA.
Every eve/AI-SDK claim in this RFC is grounded in a doc current as of this mission
(2026-07-09) as cited inline and in 11.1 above; the design is anchored to concepts, not
exact signatures, so a signature change does not by itself invalidate the architecture.
