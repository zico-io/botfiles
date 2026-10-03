---
description: Create a changeset entry for version tracking
argument-hint: "<description>"
---
Generate a changeset for the current changes.

$1

First identify which packages were modified (check git diff). Then create a changeset that describes the change and its impact using `bunx changeset`.

Format: markdown with frontmatter showing affected packages and bump type (patch, minor, major).

Guidelines:
- Summarize the change in one clear sentence
- Specify correct bump type based on semver impact
- If no user-facing changes, use `bunx changeset add --empty` instead
