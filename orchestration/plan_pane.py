#!/usr/bin/env python3
"""plan_pane.py - live-editor surface for the /scope-mission draft brief.

Opens the brief in a split herdr pane running the human's Helix (`hx`), so
they can edit and save it directly instead of dictating every change through
chat. A permanent Helix keybind (installed once via `install-keybind`) lets
the human push their current selection - file, line range, text - to a fixed
well-known path, which the orchestrator reads with `selection` to reference
exact lines/sections in chat. Save pickup is mtime-based (`file_changed_since`),
checked once per orchestrator turn - NOT a filesystem watcher.

Python 3 stdlib only, matching orchestration/spawn.py conventions (same
herdr() JSON helper style). herdr (v0.7.1, JSON over a local socket) is the
only pane interface; the `open`/`close` subcommands shell out to it and only
run on the host inside a real herdr session (HERDR_ENV=1) - they are not
exercised by this repo's sandboxed workers, see orchestration/smoke-plan-pane.py
for what IS covered in-sandbox.

Usage:
  python3 plan_pane.py open <file>             # split a pane, launch hx on <file>, print pane id
  python3 plan_pane.py close <pane-id>         # close that editor pane
  python3 plan_pane.py selection               # print + clear the last pushed selection
  python3 plan_pane.py install-keybind         # idempotently add the push-selection keybind (host only)

See .claude/commands/scope-mission.md for the human-facing workflow this supports.
"""
import json
import os
import re
import subprocess
import sys

SELECTION_PATH = "/tmp/botfile-missions/plan-selection.json"
HELIX_CONFIG = os.path.expanduser("~/.config/helix/config.toml")
HERE = os.path.dirname(os.path.abspath(__file__))
SHIM_PATH = os.path.join(HERE, "plan_pane_shim.py")

# Installed verbatim into ~/.config/helix/config.toml by install_keybind(). C-p is
# confirmed unbound in Helix's default normal-mode keymap (docs.helix-editor.com,
# 2026-07-08 check). :pipe-to discards its command's output and leaves the buffer/
# selections untouched, so this keybind is inert outside of the scratch-file write -
# see plan_pane_shim.py's docstring for the full expansion/multi-cursor reasoning.
MARKER = "# plan-pane push-selection keybind (managed by orchestration/plan_pane.py install-keybind)"
KEY_LINE = (
    f'C-p = ":pipe-to python3 {SHIM_PATH} %{{buffer_name}} %{{selection_line_start}} %{{selection_line_end}}"'
)


def herdr(*args):
    """Run a herdr command; return parsed JSON. Mirrors spawn.py's helper."""
    out = subprocess.run(["herdr", *args], capture_output=True, text=True, check=True).stdout.strip()
    if not out:
        return None
    try:
        doc = json.loads(out)
    except json.JSONDecodeError:
        return out  # `pane read` returns plain text
    if isinstance(doc, dict) and doc.get("error"):
        raise RuntimeError(f"herdr {' '.join(args)}: {doc['error'].get('message', doc['error'])}")
    return doc


def open_editor(path):
    """Split a pane off the caller's own pane (no focus stolen) and launch hx on `path`
    in it. Returns the new pane id.

    No anchor is passed (unlike spawn.py, which always splits an explicitly-created
    pane it doesn't own) - this call runs interactively from inside the orchestrator's
    own herdr pane, so a bare `pane split` is assumed to default to splitting the
    caller's active pane. HOST-E2E ASSUMPTION, unverified in this sandbox (no herdr
    socket) - confirm live."""
    split = herdr("pane", "split", "--direction", "right", "--no-focus")
    pane = split["result"]["pane"]["pane_id"]
    herdr("pane", "run", pane, f"hx {path}")
    return pane


def close_editor(pane_id):
    """Close the editor pane opened by open_editor(). `pane close` is a best-guess
    herdr verb (by analogy with spawn.py's `workspace close`/`tab create`/`pane
    split`/`pane run`) - unverified in this sandbox (no herdr socket), confirm live."""
    herdr("pane", "close", pane_id)


def parse_selection(json_text):
    """Parse a pushed-selection JSON payload (as written by plan_pane_shim.py) into
    dict(file, start_line, end_line, text). Raises ValueError/KeyError on malformed
    input - callers treat that as "nothing usable was pushed"."""
    doc = json.loads(json_text)
    return {
        "file": doc["file"],
        "start_line": int(doc["start_line"]),
        "end_line": int(doc["end_line"]),
        "text": doc["text"],
    }


def resolve_section(file_lines, start_line, end_line):
    """Walk upward from start_line to find the nearest enclosing '## ' heading in
    file_lines (0-indexed list, start_line/end_line 1-indexed). Returns
    (heading_text, heading_line_number), or (None, None) if none is found above."""
    for lineno in range(start_line, 0, -1):
        line = file_lines[lineno - 1]
        if line.startswith("## "):
            return line[3:].strip(), lineno
    return None, None


def file_changed_since(path, recorded_mtime):
    """True if `path`'s mtime is newer than recorded_mtime. Pure mtime comparison,
    checked once per call by the caller (e.g. once per orchestrator turn) - NOT a
    filesystem watcher; there is no background polling here."""
    try:
        return os.path.getmtime(path) > recorded_mtime
    except FileNotFoundError:
        return False


def read_and_clear_selection(path=SELECTION_PATH):
    """Read the pushed-selection file and delete it (a consuming read, so the next
    call sees nothing until another selection is pushed). Returns a parsed dict, or
    None if nothing was pushed since the last read, or if the file was malformed
    (treated the same as "nothing usable").

    Claims the file with an atomic rename before reading it, so a shim write that
    lands concurrently (mid read-then-delete) can't be silently dropped: it either
    beats the rename (we read it) or arrives after (it starts a fresh file, untouched
    by our delete)."""
    claim = path + ".reading"
    try:
        os.rename(path, claim)
    except FileNotFoundError:
        return None
    try:
        with open(claim) as f:
            text = f.read()
    finally:
        os.remove(claim)
    if not text.strip():
        return None
    try:
        return parse_selection(text)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def cmd_selection():
    sel = read_and_clear_selection()
    if sel is None:
        return  # nothing pushed; print nothing
    section = section_line = None
    try:
        with open(sel["file"]) as f:
            lines = f.read().splitlines()
        section, section_line = resolve_section(lines, sel["start_line"], sel["end_line"])
    except FileNotFoundError:
        pass
    print(f"file: {sel['file']}")
    print(f"lines: {sel['start_line']}-{sel['end_line']}")
    if section:
        print(f"section: ## {section} (line {section_line})")
    print("text:")
    print(sel["text"])


_CP_BOUND_RE = re.compile(r"(?m)^\s*C-p\s*=")


def install_keybind():
    """Idempotently append the push-selection keybind to the human's Helix config.
    Runs on the HOST (not in the sandbox) since it edits ~/.config/helix - this repo's
    sandboxed workers can only exercise this against a temp file, see
    orchestration/smoke-plan-pane.py. Guarded by MARKER so re-running is a no-op.

    Also guards against clobbering a user's own C-p binding: inserting a second
    `C-p = ...` line into the same [keys.normal] table would be a TOML "duplicate
    key" error that breaks their config on next hx launch, so if C-p is already
    bound (and it isn't ours) this warns and does nothing instead of writing."""
    text = open(HELIX_CONFIG).read() if os.path.exists(HELIX_CONFIG) else ""
    if MARKER in text:
        print(f"keybind already installed in {HELIX_CONFIG}")
        return
    if "[keys.normal]" in text:
        start = text.index("[keys.normal]") + len("[keys.normal]")
        end = text.find("\n[", start)
        table = text[start:] if end == -1 else text[start:end]
        if _CP_BOUND_RE.search(table):
            print(f"C-p is already bound in [keys.normal] in {HELIX_CONFIG} (not ours) - "
                  f"not installing, pick a different key or remove the existing binding first")
            return
        # Insert right after the existing table header so the new key lands in the
        # same table - TOML key order within a table doesn't matter, and this avoids
        # the "duplicate table" error a second [keys.normal] header would raise.
        text = text[:start] + "\n" + MARKER + "\n" + KEY_LINE + "\n" + text[start:]
    else:
        os.makedirs(os.path.dirname(HELIX_CONFIG), exist_ok=True)
        text = text.rstrip("\n") + ("\n\n" if text.strip() else "") + "[keys.normal]\n" + MARKER + "\n" + KEY_LINE + "\n"
    os.makedirs(os.path.dirname(HELIX_CONFIG), exist_ok=True)
    with open(HELIX_CONFIG, "w") as f:
        f.write(text)
    print(f"installed keybind in {HELIX_CONFIG}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["open"] and len(args) == 2:
        print(open_editor(args[1]))
    elif args[:1] == ["close"] and len(args) == 2:
        close_editor(args[1])
    elif args == ["selection"]:
        cmd_selection()
    elif args == ["install-keybind"]:
        install_keybind()
    else:
        sys.exit(__doc__)
