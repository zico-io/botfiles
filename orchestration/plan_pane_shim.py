#!/usr/bin/env python3
"""plan_pane_shim.py - invoked by the Helix keybind installed by
`plan_pane.py install-keybind`. Not meant to be run by hand.

Reads the piped primary-selection TEXT on stdin, takes [buffer_name,
start_line, end_line] as argv, and atomically writes them as JSON to the
fixed pushed-selection path that `plan_pane.py selection` reads.

Doc-based reasoning (Helix 25.07, verified via docs.helix-editor.com - no
local `hx` binary in this sandbox to test live; see squad-lead-plan-pane
finding post before this was built):
  - The keybind invokes this via `:pipe-to`, which pipes selection TEXT to
    this script's stdin and discards its output, leaving the buffer and
    selections unchanged - so the keybind is inert outside of this side
    effect, satisfying the "must not disturb scoping" requirement for free.
  - `%{buffer_name}`, `%{selection_line_start}`, `%{selection_line_end}` all
    resolve to the PRIMARY cursor/selection (docs describe them in terms of
    "the currently focused document" / "the primary cursor", singular) and
    are expanded before the shell command line is built - so argv here is
    always the primary selection's file + line range, regardless of how many
    selections a multi-cursor edit has.
  - CAVEAT, UNVERIFIED / to-be-confirmed in a live host E2E (no `hx` binary
    in this sandbox to test against): `:pipe-to`'s own docs say it pipes
    "each selection" to the command, which is ambiguous about whether
    multi-cursor triggers N invocations of this shim - each with a
    different selection's TEXT on stdin, but the SAME primary-cursor argv
    above (since those are fixed expansions, not per-selection). If that
    happens, only the LAST invocation's write survives (this script
    overwrites, never appends), which could pair a non-primary selection's
    text with the primary selection's line range.
  - SUPPORTED PATH: a single selection (N=1) - primary wins trivially, no
    possible mismatch. Multi-cursor pushes are unsupported until the above
    is confirmed live: collapse to one selection before pressing C-p.
"""
import json
import os
import sys

SELECTION_PATH = "/tmp/botfile-missions/plan-selection.json"


def main():
    if len(sys.argv) != 4:
        sys.exit(f"usage: {sys.argv[0]} <buffer_name> <start_line> <end_line>  (selection text on stdin)")
    buffer_name, start_line, end_line = sys.argv[1], sys.argv[2], sys.argv[3]
    text = sys.stdin.read()
    doc = {"file": buffer_name, "start_line": int(start_line), "end_line": int(end_line), "text": text}
    os.makedirs(os.path.dirname(SELECTION_PATH), exist_ok=True)
    tmp = SELECTION_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f)
    os.replace(tmp, SELECTION_PATH)  # atomic - a concurrent reader never sees a partial write


if __name__ == "__main__":
    main()
