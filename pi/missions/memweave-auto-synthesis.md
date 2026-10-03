# Mission: Automatic Memweave Synthesization

## Goal
After every mission completes, the orchestrator agent automatically synthesizes learnings into memweave memories — no manual prompting required.

## Approach
Two-layer system: prompt instruction (happy path) + extension hook (safety net).

## Changes

### 1. `mission-harness.ts` — Add Phase 5 prompt
Add a **Phase 5 — Synthesize Memories** section to `MISSION_COORDINATOR_PROMPT`:

```
**Phase 5 — Synthesize Memories**
After presenting results to the user, automatically:
1. Review subagent reports and the full mission context
2. Call `mem_search` with relevant keywords to find existing related memories
3. Call `mem_write` to create/update memories:
   - Use dated filenames (YYYY-MM-DD-<slug>.md) for session digests
   - Use evergreen slugs (preferences, conventions, etc.) for persistent facts
   - For updates: search, read the existing memory, then write the updated version
4. Be concise — one memory per distinct topic, not one per fact
```

### 2. Safety-net hook
Add to `memweave/index.ts` (or a new extension):
- Hook `session_before_switch` event
- Track whether orchestration tools (subagent, fleet_boot, orchestrate_*) were called during the session
- Also track whether `mem_write` was called
- If orchestration happened but no synthesis occurred, inject one final turn prompting the LLM to synthesize before the session closes

### 3. What synthesis produces
- **Dated digests**: `YYYY-MM-DD-<mission-slug>.md` — what happened, what was decided
- **Evergreen updates**: `preferences.md`, `conventions.md`, etc. — persistent facts that survive

## Squad assignments

| Step | Agent | Task |
|------|-------|------|
| 1 | Worker | Add Phase 5 prompt to `mission-harness.ts` |
| 2 | Worker | Add safety-net hook to `memweave/index.ts` |
| 3 | Reviewer | Review both changes for correctness |

## Sequence
Build → Review → Fix (if needed) → Done
