---
description: Generate a conventional commit message from staged changes
argument-hint: "[instructions]"
---
Generate a conventional commit message for the staged changes.

Instructions: ${1:-Use git diff --staged to see the changes, then generate a commit message.}

Format: `<type>(<scope>): <description>`

Types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert
Scope: the affected package or component (use the Turborepo package name)

Guidelines:
- Description under 72 characters, imperative mood ("add" not "added")
- Include breaking changes with `BREAKING CHANGE:` footer if applicable
- Reference related issues (#123)
- Be specific about what changed and why
- No em dashes

First run `git diff --staged` to see what changed, then produce the commit message.
