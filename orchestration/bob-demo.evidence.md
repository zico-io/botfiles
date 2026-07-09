# bob-demo evidence: eve worker indistinguishable in a live mixed fleet

Mission eve-harness-v0 / RFC S9 step 3. Demo run 2026-07-09T19:29:04Z.
Fleet: demo-lead (claude/opus), worker-claude (claude/sonnet), worker-eve (EVE) in squad-demo-lead.
Same identical task given to worker-claude and worker-eve; both reported the same way.

## Connector liveness (status)
```
  orbal-net server: pid 68170 ALIVE  http://192.168.12.47:50079
  eve connector (worker-eve in squad-demo-lead): UP  pid 392
  agents: demo-lead(active), orchestrator(active), worker-claude(active), worker-eve(active)
```

## Room thread (squad-demo-lead) - both post normal messages, indistinguishable
```
--- [5] demo-lead ---
TASK for BOTH worker-claude AND worker-eve (identical). Each of you independently: complete the task below and report exactly as specified.

TASK: Write a 3-sentence explanation of what makes a good git commit message, then give one good one-line example.

REPORTING (each of you, in this room squad-demo-lead):
1. emit event kind=task-start with task='commit-msg-guide' (orbal-net event squad-demo-lead task-start --task 'commit-msg-guide')
2. emit a progress step 1/1 (orbal-net progress squad-demo-lead 1/1)
3. post your answer as a normal room message (orbal-net send squad-demo-lead ...)
4. emit event kind=task-done with task='commit-msg-guide' (orbal-net event squad-demo-lead task-done --task 'commit-msg-guide')

Please start now.

--- [6] worker-claude ---
A good git commit message summarizes the change in a short imperative-mood subject line (under ~50 chars) so it reads clearly in log output. The body, if needed, explains why the change was made and any tradeoffs, not just what changed, since the diff already shows that. Each commit should represent one logical change, making the message easy to write concisely and easy for others to scan later. Example: 'fix: prevent race condition in session token refresh'

--- [7] worker-eve ---
A good git commit message summarizes the change in a short imperative subject line (under ~50 chars) so it reads clearly in logs. It focuses on why the change was made, not just what changed, since the diff already shows the what. It stays scoped to one logical change, avoiding unrelated edits bundled together.

Example: "Fix null pointer crash when user profile is empty"

--- [8] worker-claude ---
commit-msg-guide done

```

## Typed events (squad-demo-lead) - IDENTICAL lifecycle shape per worker
```
worker-eve     task-start  task=ack-ready        step=None/None
worker-eve     task-done   task=ack-ready        step=None/None
worker-claude  task-start  task=commit-msg-guide step=None/None
worker-eve     task-start  task=commit-msg-guide step=None/None
worker-claude  step        task=None             step=1/1
worker-eve     step        task=None             step=1/1
worker-claude  task-done   task=commit-msg-guide step=None/None
worker-eve     task-done   task=commit-msg-guide step=None/None
```

## Verdict
orbal-net peek/events (the same feed the tui room-thread + per-agent progress panel render)
cannot distinguish worker-eve from worker-claude: same message shape, same task-start/step/task-done
event schema, first-class identity in orbal-net agents, connector UP. PASS.
