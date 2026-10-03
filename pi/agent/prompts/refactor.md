---
description: Safe refactoring with verification steps
argument-hint: "<target>"
---
Refactor $1. Follow these principles:

Before making changes:
1. Read the current code thoroughly
2. Identify all callers/references (grep for usages)
3. Understand the current behavior including edge cases

During refactoring:
1. Make minimal, targeted changes - one logical change at a time
2. Preserve existing behavior exactly
3. Follow project conventions (file structure, naming, patterns)
4. Keep the diff small and reviewable

After refactoring:
1. Verify all imports are updated
2. Run `bun run check-types` to ensure type safety
3. Run `bun run test` to verify existing tests pass
4. Run `bun run lint` to check formatting
5. If tests exist, update them for any interface changes
