---
name: issue-intake
description: Drafts, checks for duplicates, and files Linear issues from bug reports, feature requests, and chores. Use when someone asks to capture a report or file a Linear ticket; for example, "file checkout failing on coupon apply". Not for reading a ticket, grooming an existing issue, or creating GitHub issues.
---

# Issue intake

Use the reporter's request and inspected evidence to file one issue per finding.
The shared runtime authority is `@repo/issues/intake` in Bask-Health/bots, backed
by `@repo/linear`. Do not add another GraphQL client or copy its policy into a
new runtime.

## Context

Choose the reference for the available tool surface:

- With `issues__file`, read [references/fleet.md](references/fleet.md). This is
  the fleet's existing intake contract, including private-channel handoff,
  evidence transfer, customer needs, and authenticated filing.
- With direct Linear MCP tools in a T3/terminal session, read
  [references/desktop.md](references/desktop.md). Preserve the session's user
  identity and explicitly report runtime-only features that are unavailable.

## Steps

1. Extract the finding, scope and observed impact. Ask only for information
   needed to distinguish the failure or route it. Never invent a reproduction,
   affected tenant, verification result or source link.
2. Search for open duplicates in the owning team. Report a strong match and
   offer to use the existing issue; do not silently create another.
3. Draft compact, evidenced engineering context. Keep reporter words distinct
   from conclusions and source metadata distinct from the body.
4. File through the selected adapter when authorized by the user's request.
   A request to draft or preview authorizes preparation only. Follow an explicit
   request for review before filing.
5. Report `[IDENTIFIER](url)` from the actual result, and any partial failure.

## Gotchas

- `linear-issue` in this repository reads and analyzes tickets. Creation is
  `create-issue` or this skill; keep those names distinct.
- Fleet tools infer routing, priority and labels. Never bypass `issues__file`
  with a direct save when that tool is available.
- A failed write can have succeeded upstream. Inspect Linear before retrying;
  stop on authentication/scope failures until an operator fixes the connection.
- Do not retry a successful issue save because a source comment, attachment or
  customer need failed. Report the partial result without creating a duplicate.
- Do not publish credentials, PHI, private provider URLs or raw logs in tickets.

## Verify

- Duplicate search completed and every claim is tied to available evidence.
- Creation used the available runtime adapter under the requested authority.
- The identifier and URL came from Linear, with partial failures disclosed.

## Update scaffold

Policy belongs here; deterministic filing behavior belongs in `@repo/issues`
and `@repo/linear`. Sync this directory into consumers using
`scripts/sync-linear-skills.py`; edit this source rather than generated copies.
