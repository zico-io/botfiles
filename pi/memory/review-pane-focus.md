# Agent pane focus etiquette

When an agent spawns a herdr pane (e.g. `scripts/review-pane`), it must only change focus *within its own workspace*. If the user is currently viewing a different workspace (check `herdr workspace list` → the entry with `focused: true` vs `$HERDR_WORKSPACE_ID`), do NOT steal focus — open the pane with `--no-focus` and fire `herdr notification show` instead.

**Why:** yanking the user's view to another workspace mid-task is disruptive.
**How to apply:** gate the `herdr pane split` focus flag on whether the focused workspace equals the agent's own; notify on mismatch.