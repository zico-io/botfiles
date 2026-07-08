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

Right after writing the brief, open it in a live editor pane so the human can edit it
directly instead of dictating every change through chat:

```
python3 orchestration/plan_pane.py open orchestration/$ARGUMENTS.brief.md
```

This splits a right-hand herdr pane running the human's Helix (`hx`) on the brief without
stealing focus, and prints the new pane id. Remember that pane id - you close it at
hand-off. If the command fails (no herdr socket, Helix missing), say so and fall back to
plain chat-driven editing; the rest of the interview still works.

## 3. Collaborate on the brief through the pane

From now until hand-off the brief is a shared surface: the human edits and saves it in the
pane, and pushes selections to you with the Helix keybind (see
`orchestration/plan_pane.py install-keybind`). The pane never interrupts you - it is
passive until your turn. So **before composing each response**, do two cheap checks:

1. **Pick up saves.** Re-read `orchestration/$ARGUMENTS.brief.md` (its mtime changes on
   `:w`). If the human changed it, treat the file on disk as the source of truth, fold
   their edits into your understanding, and do not clobber them - your next write must
   build on their version, not overwrite it.
2. **Pick up selections.** Run:

   ```
   python3 orchestration/plan_pane.py selection
   ```

   It prints (and clears) any pushed selection: the file, the line range, the enclosing
   `##` section, and the selected text. Empty output means nothing was pushed. When a
   selection is present, reference it directly - quote the selected lines and name the
   section and line numbers ("in ## Non-goals, lines 22-24, you selected ...") so the
   human knows you are looking at exactly what they marked. Multi-cursor selections
   collapse to the primary selection.

Keep interviewing and refining the brief in this loop. Write your edits back to the file
so the human sees them appear in the pane.

## 4. Draft the roster

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

## 5. Hand off

Close the editor pane you opened in step 2 (use the pane id it printed):

```
python3 orchestration/plan_pane.py close <pane-id>
```

Then finish by telling the human the two files are written and pointing them at:
`/spawn-team orchestration/$ARGUMENTS.roster.json` (run from inside herdr). Remind them
`up` will auto-post the brief into the mission room - no manual step.
