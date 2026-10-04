---
name: create-issue
description: >
  Creates a Linear ticket or a GitHub issue for Bask, using the shared issue-intake policy
  for Linear and repository templates for GitHub. Use when the user asks to file a bug, create a ticket, open an issue,
  write up a task, or says /create-issue. Not for grooming an existing triage queue
  (use /linear-triage-groomer) or scaffolding a project (use /linear-project-manager).
  Usage - /create-issue checkout 500s on coupon apply, /create-issue github behemoth rack labels overlap
argument-hint: "[linear|github] <description of the issue>"
compatibility: Claude Code and Codex with authenticated Linear tools or gh for GitHub issues.
---

# Create Issue

File an issue for: **$ARGUMENTS**

## Choose the target

Use Linear for Bask product/platform reports. Use GitHub when the user requests
it or the work belongs to a repository's issue tracker. Resolve an ambiguous
target before filing.

## Linear tickets

Load [the shared issue-intake skill](../issue-intake/SKILL.md) and follow its
runtime adapter. It owns duplicate search, drafting, team routing and filing.
Do not maintain separate description, status, priority or label policies here.

## GitHub issues

Use GitHub only for work that lives in a public or repo-scoped context. Product and
platform work goes to Linear.

Known repos (confirm with `git -C <repo> remote get-url origin` rather than assuming):

| Repo | What |
|------|------|
| `bask-health/lash-platform-admin` | Main platform monorepo |
| `Bask-Health/behemoth` | Rack topology visualizer |
| `bask-health/base-ui` | Standalone UI component library |
| `bask-health/docs-v2` | Documentation site |

### Body

```markdown
### Description
[What is broken or being proposed]

### Steps to reproduce
1. [Step]

### Expected behavior
[What should happen]

### Environment
- Repo / branch:
- Node / pnpm version:
- OS:
```

### Create it

1. `gh auth status` to confirm authentication.
2. Check for an issue template: `ls .github/ISSUE_TEMPLATE/`. If one exists, follow
   it instead of the body above.
3. Preview title, body, and target repo. Wait for confirmation.
4. Create:
   ```bash
   gh issue create --repo <owner/repo> --title "<title>" --body "$(cat <<'EOF'
   <body>
   EOF
   )"
   ```
5. Report the number and URL.

---

## Cross-linking

When both a Linear ticket and a GitHub issue exist for the same problem, link them:
the GitHub URL as an attachment on the Linear ticket, and the Linear URL in the
GitHub issue body. Offer this whenever the user mentions the counterpart exists.

---

## Gotchas

- Resolve the target repository from its git remote rather than an assumed name.
- After a write error, inspect the target before retrying to avoid duplicates.

## Verify

- The intended tracker and repository/team were resolved.
- A duplicate search ran and the write matched the user's authorization.
- The returned issue identifier and URL came from the actual tool result.

## Update scaffold

Update `build/issue-intake` for Linear policy changes, then sync its consumers
with `scripts/sync-linear-skills.py`. Keep GitHub-specific behavior here.
