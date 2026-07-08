---
description: Interview the human to scope an ambiguous mission, then write its brief and draft its roster
argument-hint: <feature>
---

You are the **orchestrator** (layer 1). The human has a mission whose feature name is
`$ARGUMENTS`, but the task is under-specified. Before any fleet spawns, your job is to
turn it into a well-scoped **brief** and a **roster** - the mission's guiding light.
Do not spawn anything here; this command only produces the two artifacts.

Work collaboratively - interview, do not dictate. Use `AskUserQuestion` to gather each
dimension below, one focused question (or a small batch) at a time. Default sensibly
when the human is vague, state the default you chose, and let them correct it. Keep
digging until the scope is unambiguous enough that a lead could execute without guessing.

## 1. Interview

Cover these dimensions (skip any the human has already made clear):

- **Goal** - the problem and the desired outcome. Why now, what does success look like.
- **In scope** - the concrete work this mission covers.
- **Non-goals** - what it explicitly does NOT touch. This is where ambiguity hides;
  press for it.
- **Constraints** - tech stack, backward-compat, performance, deadlines, must-use or
  must-avoid dependencies.
- **Acceptance criteria** - how we know it is done: behaviors to demonstrate, tests to
  pass, gates to stay green.
- **Affected areas** - repos, files, subsystems, entry points the change touches.
- **Risks / unknowns** - what could go wrong or needs investigation first.
- **Team plan** - the target `repo` path, and which teams (layer-2 leads, each with its
  layer-3 workers) the mission needs. Keep to the minimum. For each agent settle
  `role`, `harness` (claude / codex / pi), and `model`.

## 2. Write the brief

Write `orchestration/$ARGUMENTS.brief.md` (plain markdown, no provenance footer - it is
a work artifact, not a memory fact; no em dashes, use `-`). One section per dimension:

```markdown
# Mission brief: <feature>

## Goal
...

## In scope
- ...

## Non-goals
- ...

## Constraints
- ...

## Acceptance criteria
- ...

## Affected areas
- ...

## Risks and unknowns
- ...

## Team plan
- <lead-role> (harness/model): <what this team owns>
  - <worker-role> (harness/model): <what this worker does>
```

`spawn.py up` posts this file into the `mission-<feature>` room as its first message, and
each lead reads and relays it to its squad - so write it to be read cold by an agent with
no other context.

## 3. Draft the roster

Write `orchestration/$ARGUMENTS.roster.json` from the team plan, matching
`orchestration/roster.example.json`:

```json
{
  "feature": "<feature>",
  "repo": "<repo path>",
  "roles": [
    {"role": "lead-x",     "parent": "orchestrator", "harness": "claude", "model": "opus"},
    {"role": "worker-x-1", "parent": "lead-x",       "harness": "claude", "model": "sonnet"}
  ]
}
```

Rules: `feature` must equal `$ARGUMENTS`. Every lead has `parent: "orchestrator"`; every
worker's `parent` is its lead's `role`; max 3 layers, workers are leaves. Defaults when
the human did not specify: `harness: "claude"`, lead `model: "opus"`, worker
`model: "sonnet"`. If the file already exists, update it rather than clobbering unrelated
teams. Show the human the drafted roster and let them adjust before you finish. Validate
it with `python3 orchestration/spawn.py selfcheck` is not enough - the hierarchy check
runs inside `up`; sanity-check by eye that it parses and the parent links are sound.

## 4. Hand off

Finish by telling the human the two files are written and pointing them at:
`/spawn-team orchestration/$ARGUMENTS.roster.json` (run from inside herdr). Remind them
`up` will auto-post the brief into the mission room - no manual step.
