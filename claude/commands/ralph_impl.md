---
disable-model-invocation: true
description: >-
  Use when starting implementation on a small (XS/S) Linear ticket — picks the
  highest-priority ready-for-dev ticket automatically, or accepts a specific
  ticket ID. Sets up a git worktree, then launches a sub-agent to implement the
  plan and produce a commit, draft PR against staging, and a Linear comment with
  the PR link. Not for planning (use /ralph_plan), large tickets, or tickets
  without an existing implementation plan. Usage — /ralph_impl [ticket-id]
model: sonnet
---

## PART I - IF A TICKET IS MENTIONED

0c. use `linear` cli to fetch the selected item into thoughts with the ticket number - ./thoughts/shared/tickets/ENG-xxxx.md
0d. read the ticket and all comments to understand the implementation plan and any concerns

**Exit when:** ticket fetched and plan understood.

## PART I - IF NO TICKET IS MENTIOND

0.  read .claude/commands/linear.md
0a. fetch the top 10 priority items from linear in status "ready for dev" using the MCP tools, noting all items in the `links` section
0b. select the highest priority SMALL or XS issue from the list (if no SMALL or XS issues exist, EXIT IMMEDIATELY and inform the user)
0c. use `linear` cli to fetch the selected item into thoughts with the ticket number - ./thoughts/shared/tickets/ENG-xxxx.md
0d. read the ticket and all comments to understand the implementation plan and any concerns

**Exit when:** ticket selected, fetched, and plan understood.

## PART II - NEXT STEPS

1. move the item to "in dev" using the MCP tools
1a. identify the linked implementation plan document from the `links` section
1b. if no plan exists, move the ticket back to "ready for spec" and EXIT with an explanation

2. set up worktree for implementation:
2a. read `hack/create_worktree.sh` and create a new worktree with the Linear branch name: `./hack/create_worktree.sh ENG-XXXX BRANCH_NAME`
2b. launch implementation session: `claude --model opus --dangerously-skip-permissions --verbose -p "/implement_plan and when you are done implementing and all tests pass: (1) run /commit-smart to create a commit, (2) run /commit-context to write the PR description and open a draft PR against staging, then add a comment to the Linear ticket with the PR link, (3) run /commit-context to post commit context to the PR, (4) run /compact"` (run from `~/wt/bask/ENG-XXXX`)

**Success:** sub-agent exits after posting the PR link as a Linear comment. Verify on the ticket.

Use TodoWrite to track tasks. When fetching from Linear, get the top 10 items by priority but work on ONE — the highest priority SMALL or XS issue.
