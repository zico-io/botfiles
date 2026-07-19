---
name: linear-issue
description: "Create a well-formed Linear issue from the terminal. Use when the user asks to create, file, open, or log a Linear issue or ticket, to 'track this in Linear', to turn a bug/task/idea into an issue, or when a pre-push hook or review warns that work is untracked and an issue is needed. Handles resolving the team, writing a clean title and description, setting priority/labels/assignee, and returning the identifier and URL. Do NOT use for updating issue status or roadmap prose (Linear's UI/integration owns status sync); this is for creating new issues."
license: MIT
metadata:
  author: gilbert
  version: '1.0'
---

# Linear Issue

## When to Use This Skill

Use when the user wants to create a new Linear issue: "file this in Linear", "make a ticket", "track this work", "open an issue for the bug we just found", or when a warning (pre-push hook, PR check, review) says work has no Linear reference and one should be created.

Do NOT use this to change status, priority ordering, or roadmap discussion on existing issues - Linear's UI and its GitHub integration own status sync. This skill only *creates* issues.

## Prerequisites

- A **personal API key**: Linear -> Settings -> Security & access -> Personal API keys. Store it as `LINEAR_API_KEY` in the environment (never paste it into chat or commit it).
- If a Linear MCP server is connected in this session, prefer its issue-create tool over raw GraphQL - it handles auth and ids for you. Fall back to the API below when no MCP is available.
- The **team key** (the uppercase prefix in identifiers, e.g. `ROG` for `ROG-42`). Ask if unknown; do not guess.

Auth note: Linear personal API keys go **directly** in the `Authorization` header with no `Bearer` prefix.

## Procedure

1. **Confirm the essentials** before creating anything:
   - Team key (e.g. `ROG`).
   - A concise title (see conventions).
   - A one-to-three sentence description, plus acceptance criteria if the work has a clear "done".
   If the user gave enough context to write these, do not interrogate them - draft it and create.

2. **Resolve the team id** from its key:

   ```bash
   curl -sf https://api.linear.app/graphql \
     -H "Authorization: $LINEAR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"query":"query($key:String!){teams(filter:{key:{eq:$key}}){nodes{id name}}}","variables":{"key":"ROG"}}' \
     | jq -r '.data.teams.nodes[0].id'
   ```

3. **Create the issue.** Pass fields as GraphQL variables so titles/descriptions with quotes or newlines are safe. `description` is Markdown. Optional inputs: `priority` (0 none, 1 urgent, 2 high, 3 normal, 4 low), `labelIds`, `assigneeId`.

   ```bash
   TEAM_ID="<id from step 2>"
   jq -n \
     --arg teamId "$TEAM_ID" \
     --arg title "Prevent duplicate save files on crash" \
     --arg description "The autosave path is not fsync'd, so a crash mid-write leaves a truncated save.\n\n## Acceptance\n- Autosave writes to a temp file and renames atomically.\n- A crash during save never corrupts the previous save." \
     '{query:"mutation($teamId:String!,$title:String!,$description:String!){issueCreate(input:{teamId:$teamId,title:$title,description:$description,priority:3}){issue{identifier url}}}",variables:{teamId:$teamId,title:$title,description:$description}}' \
   | curl -sf https://api.linear.app/graphql \
       -H "Authorization: $LINEAR_API_KEY" \
       -H "Content-Type: application/json" \
       -d @- \
   | jq -r '.data.issueCreate.issue | "\(.identifier)  \(.url)"'
   ```

4. **Report back** the identifier and URL. If the work already has a branch or open PR, tell the user to put the identifier in the branch name (Linear's suggested `name/rog-42-slug` form) or a commit/PR title so the GitHub integration links it automatically.

### Optional lookups (only when the user asks to set them)

- **Labels**: `query($id:String!){team(id:$id){labels{nodes{id name}}}}` - match by name, pass matching ids as `labelIds:[...]`.
- **Assignee (self)**: `query{viewer{id}}` - use for "assign it to me".
- **Workflow state**: issues default to the team's backlog/triage state; only set `stateId` if the user explicitly wants a different starting column.

## Title and Description Conventions

- **Title**: imperative, specific, no ticket-speak. "Add fog-of-war to the map renderer", not "FOV stuff" or "As a user I want...". No trailing period. Aim under ~70 chars.
- **Description**: state the problem or goal first, then acceptance criteria as a checklist when the work has a definite done. Keep it durable - link to a PR/commit for implementation detail rather than pasting code.
- **One issue per unit of work.** If the user describes several independent things, create several issues and report all identifiers.
- Do not invent scope, priority, or labels the user did not imply. Default priority to normal (3) unless told otherwise.

## Failure Handling

- Missing/invalid key: `curl` returns an auth error. Tell the user to set `LINEAR_API_KEY`; do not proceed.
- Empty team lookup: the team key is wrong or the key lacks access. Confirm the key with the user.
- A GraphQL response with a top-level `errors` array is a failure even with HTTP 200 - surface the message, do not report success.
- Never fabricate an identifier or URL. Only report what the API returned.
