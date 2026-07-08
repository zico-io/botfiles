# Mission brief: plan-pane

## Goal
Scoping a mission today is chat-only: the orchestrator interviews the human and the draft brief is edited by proxy through conversation. Make the plan a first-class editing surface. During /scope-mission the draft brief opens in a split herdr pane running the user's $EDITOR (Helix), the user edits and saves it directly, the orchestrator picks up saves, and a Helix keybind pushes the current selection (file, line range, text) to a well-known file so the orchestrator can reference exact lines and sections in the chat pane.

## In scope
- New `orchestration/plan_pane.py` (Python 3 stdlib only, next to spawn.py):
  - `open <file>`: split a pane via `herdr pane split --no-focus` plus `herdr pane run` launching `hx <file>`; print the new pane id.
  - `close <pane-id>`: close the editor pane.
  - `selection`: read (and clear) the pushed-selection file, printing file path, line range, and selected text.
  - A save-detection helper based on file mtime (compare against a recorded timestamp).
- A Helix keybind added permanently to `~/.config/helix/config.toml` that writes the primary selection text plus buffer name and line range to a fixed well-known path (for example `/tmp/botfile-missions/plan-selection.json`), using Helix 25.07 command expansions and/or `:pipe-to`.
- Update `.claude/commands/scope-mission.md` so the orchestrator drives the pane:
  - After drafting the brief, open it in the editor pane.
  - Before composing each response, re-read the brief if its mtime changed and check the selection file.
  - When a selection was pushed, resolve it to the enclosing `##` section and line numbers and reference it directly in chat.
  - Close the pane at hand-off.

## Non-goals
- No live cursor tracking and no statusline parsing; selection awareness comes only from explicit keybind pushes.
- Helix-only. Other editors degrade to plain pane editing with no selection push.
- No comms server involvement (scoping runs before any fleet exists) and no spawn.py fleet-lifecycle changes.
- No Rust changes: comms CLI, server, and TUI are untouched.
- The roster is not opened in the pane; it stays inline in chat.
- A selection push never pokes or interrupts the orchestrator pane; it is passive until the user's next chat turn.

## Constraints
- Python 3 stdlib only, matching spawn.py conventions; the herdr CLI (v0.7.1, JSON over local socket) is the only pane interface.
- Helix 25.07.1 syntax for the keybind; it must be inert outside scoping (pressing it only writes a scratch file, no other side effects).
- The selection file path is fixed and documented so the orchestrator needs no session state to find it.
- No em dashes in any written artifact; use "-".

## Acceptance criteria
- `python3 orchestration/plan_pane.py open orchestration/x.brief.md` run from inside a herdr pane opens the file in hx in a right split without stealing focus; `close` removes the pane.
- Edit plus `:w` in hx, then a chat turn, yields an orchestrator response reflecting the saved content.
- Select lines in hx, hit the keybind, ask "what about this?" in chat: the orchestrator quotes the selected lines and names the enclosing `##` section.
- A full /scope-mission dry run uses the pane end to end: draft, iterate on saves and selections, hand off.
- A self-contained smoke check exists (pattern: the comms-tui smoke test); manual steps are acceptable for the interactive parts.

## Affected areas
- `orchestration/plan_pane.py` (new)
- `.claude/commands/scope-mission.md`
- `~/.config/helix/config.toml` (one keybind addition)
- `.botfile/memory/tools/orchestration.md` (record the new surface after landing)

## Risks and unknowns
- The exact Helix incantation to emit selection text AND line range in one keybind: `:pipe-to` gives the text, `%{cursor_line}` gives position; combining them may need a tiny shell shim. Verify on Helix 25.07.1 before building around it.
- Multi-cursor selections: primary selection wins; define and document this.
- Orchestrator pane-id discovery from inside its own pane: reuse spawn.py's herdr JSON helpers.
- Save pickup is mtime-checked at the orchestrator's turn, not a filesystem watcher. This is deliberate since the orchestrator only acts at its own turns; do not build a watcher.

## Team plan
- lead-plan-pane (claude/opus): owns the design and the scope-mission.md workflow integration; reviews and merges worker output; runs the E2E verification inside herdr.
  - worker-pane (claude/sonnet): builds plan_pane.py, the Helix keybind, the selection file format, and the smoke check.
