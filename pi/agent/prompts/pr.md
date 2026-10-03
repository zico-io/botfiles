---
description: Generate a well-structured PR description from the diff
argument-hint: "[instructions]"
---
Generate a pull request description for the current changes.

${1:-Use git diff against the base branch to see what changed.}

Structure:
```markdown
## What

Brief summary of the changes.

## Why

Rationale for the changes. Link related issues (#123).

## How

Key implementation decisions. Mention tradeoffs or alternatives considered.

## Testing

How to test these changes. Include commands to run.

## Screenshots (if UI changes)

Before/after if applicable.
```

Be concise. Focus on what matters to reviewers. Follow Conventional Commits format.
