# Mission Harness: Diff Review Before Merge

**Date:** 2026-07-11

**Change:** Added Phase 4.5 to the mission harness prompt — when squads report complete, the orchestrator MUST:
1. Generate a working-tree diff (`git diff HEAD > /workspace/mission-review.patch`)
2. Open it in hunk's TUI via the `review` tool (`kind: "patch"`)
3. Call `ask_user(type="confirm")` for explicit user approval
4. Only after approval, merge into host branch

**Rationale:** Prevent squads from merging unreviewed changes. User gets a TUI diff review before anything lands.

**What was NOT done:** No new tools or extensions — existing `review` + `ask_user` + `bash` are sufficient.

**False positives:** LSP reports "Expected semicolon" on lines inside the template literal (markdown content with backticks). These are cosmetic and harmless — the template literal bounds are correct.
