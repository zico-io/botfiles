#!/usr/bin/env python3
"""Smoke test for plan_pane.py. Self-contained: exercises every pure/testable
function directly (parse_selection, resolve_section, file_changed_since,
install_keybind idempotency) plus an end-to-end round trip through the real
plan_pane_shim.py subprocess and plan_pane.py's own selection file. No herdr
socket, no Helix binary, no network. Exits 0 iff every check passes.

    python3 orchestration/smoke-plan-pane.py

NOT covered here (herdr/hx are unavailable in this sandbox - see
plan_pane.py's module docstring): open/close (shells out to herdr) and the
live Helix keybind itself (needs a real hx + a live pane). Manual steps for
those, run on the host inside a real herdr session:

  1. `python3 orchestration/plan_pane.py install-keybind` - then open Helix,
     confirm `C-p` is bound (`:pipe-to python3 .../plan_pane_shim.py ...`
     appears once in `~/.config/helix/config.toml`, run it twice and confirm
     it prints "already installed" the second time).
  2. `python3 orchestration/plan_pane.py open <some-file>` - confirm a new
     pane appears to the right, running `hx <some-file>`, without stealing
     focus; note the printed pane id.
  3. In that pane, select some text (visual/select mode) and press `C-p`.
     Confirm the buffer is unchanged (pipe-to is inert) and that
     `python3 orchestration/plan_pane.py selection` prints the file, line
     range, and the exact text you selected - then prints nothing on a
     second immediate run (consuming read).
  4. `python3 orchestration/plan_pane.py close <pane-id>` - confirm the pane
     closes.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SHIM = os.path.join(HERE, "plan_pane_shim.py")

spec = importlib.util.spec_from_file_location("plan_pane", os.path.join(HERE, "plan_pane.py"))
plan_pane = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan_pane)


def check_parse_selection():
    good = plan_pane.parse_selection(json.dumps({"file": "a.md", "start_line": 3, "end_line": 5, "text": "hi"}))
    if good != {"file": "a.md", "start_line": 3, "end_line": 5, "text": "hi"}:
        return False
    try:
        plan_pane.parse_selection(json.dumps({"file": "a.md"}))  # missing keys
        return False
    except (KeyError, TypeError):
        pass
    return True


def check_resolve_section():
    lines = [
        "# Title",
        "",
        "## Goal",
        "goal text",
        "",
        "## Non-goals",
        "line a",
        "line b",
        "line c",
    ]
    # selection inside "## Non-goals" (1-indexed lines 7-8)
    section, lineno = plan_pane.resolve_section(lines, 7, 8)
    if section != "Non-goals" or lineno != 6:
        return False
    # selection above any heading
    section2, lineno2 = plan_pane.resolve_section(["no heading here", "still none"], 1, 2)
    return section2 is None and lineno2 is None


def check_file_changed_since():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        path = f.name
    try:
        t0 = os.path.getmtime(path)
        no_change = not plan_pane.file_changed_since(path, t0 + 1)  # recorded mtime in the future -> unchanged
        time.sleep(0.01)
        os.utime(path, (t0 + 5, t0 + 5))  # force mtime forward regardless of fs timestamp resolution
        changed = plan_pane.file_changed_since(path, t0)
        missing = not plan_pane.file_changed_since(path + ".does-not-exist", t0)
        return no_change and changed and missing
    finally:
        os.remove(path)


def check_install_keybind_idempotent():
    with tempfile.TemporaryDirectory() as d:
        cfg = os.path.join(d, "config.toml")
        orig = plan_pane.HELIX_CONFIG
        plan_pane.HELIX_CONFIG = cfg
        try:
            plan_pane.install_keybind()
            first = open(cfg).read()
            first_ok = plan_pane.MARKER in first and plan_pane.KEY_LINE in first
            plan_pane.install_keybind()  # second run: must be a no-op
            second = open(cfg).read()
            idempotent = second == first and second.count(plan_pane.MARKER) == 1
            return first_ok and idempotent
        finally:
            plan_pane.HELIX_CONFIG = orig


def check_install_keybind_merges_existing_table():
    with tempfile.TemporaryDirectory() as d:
        cfg = os.path.join(d, "config.toml")
        with open(cfg, "w") as f:
            f.write('theme = "term16_dark"\n\n[keys.normal]\nC-s = ":w"\n')
        orig = plan_pane.HELIX_CONFIG
        plan_pane.HELIX_CONFIG = cfg
        try:
            plan_pane.install_keybind()
            text = open(cfg).read()
            one_table = text.count("[keys.normal]") == 1
            kept_existing = 'C-s = ":w"' in text
            added_new = plan_pane.KEY_LINE in text
            return one_table and kept_existing and added_new
        finally:
            plan_pane.HELIX_CONFIG = orig


def check_install_keybind_respects_existing_cp():
    with tempfile.TemporaryDirectory() as d:
        cfg = os.path.join(d, "config.toml")
        with open(cfg, "w") as f:
            f.write('[keys.normal]\nC-p = ":some-other-command"\n')
        orig = plan_pane.HELIX_CONFIG
        plan_pane.HELIX_CONFIG = cfg
        try:
            plan_pane.install_keybind()
            text = open(cfg).read()
            untouched = text == '[keys.normal]\nC-p = ":some-other-command"\n'
            not_ours = plan_pane.MARKER not in text
            return untouched and not_ours
        finally:
            plan_pane.HELIX_CONFIG = orig


def check_selection_claim_is_atomic_rename():
    # read_and_clear_selection() must claim via rename (not read-then-delete), so a
    # write racing the read can't be silently lost. Simulate the race directly: a
    # writer's os.replace() into `path` happening AFTER our rename-claim must survive
    # as a fresh file, not get deleted by our cleanup of the claimed copy.
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "plan-selection.json")
        with open(path, "w") as f:
            json.dump({"file": "a.md", "start_line": 1, "end_line": 1, "text": "first"}, f)
        first = plan_pane.read_and_clear_selection(path)
        # simulate a concurrent push landing right after our claim+delete
        with open(path, "w") as f:
            json.dump({"file": "a.md", "start_line": 2, "end_line": 2, "text": "second"}, f)
        second = plan_pane.read_and_clear_selection(path)
        no_claim_file_left = not os.path.exists(path + ".reading")
        return (first and first["text"] == "first" and second and second["text"] == "second"
                and no_claim_file_left)


def check_shim_round_trip():
    # Point the shim + reader at an isolated file so this never touches the real
    # /tmp/botfile-missions/plan-selection.json used by a live mission.
    with tempfile.TemporaryDirectory() as d:
        sel_path = os.path.join(d, "plan-selection.json")
        env = dict(os.environ)
        shim_src = open(SHIM).read().replace(
            'SELECTION_PATH = "/tmp/botfile-missions/plan-selection.json"',
            f'SELECTION_PATH = {sel_path!r}',
        )
        shim_copy = os.path.join(d, "shim.py")
        with open(shim_copy, "w") as f:
            f.write(shim_src)

        r = subprocess.run([sys.executable, shim_copy, "brief.md", "12", "14"],
                           input="selected text\nline two\n", capture_output=True, text=True, env=env)
        if r.returncode != 0:
            return False
        written = plan_pane.read_and_clear_selection(sel_path)
        if written != {"file": "brief.md", "start_line": 12, "end_line": 14, "text": "selected text\nline two\n"}:
            return False
        second_read = plan_pane.read_and_clear_selection(sel_path)  # consuming: nothing left
        return second_read is None and not os.path.exists(sel_path)


def main():
    checks = [
        ("parse_selection: valid + malformed", check_parse_selection()),
        ("resolve_section: nearest heading + none-above", check_resolve_section()),
        ("file_changed_since: unchanged/changed/missing", check_file_changed_since()),
        ("install_keybind: idempotent re-run", check_install_keybind_idempotent()),
        ("install_keybind: merges into existing [keys.normal]", check_install_keybind_merges_existing_table()),
        ("install_keybind: refuses to clobber an existing C-p", check_install_keybind_respects_existing_cp()),
        ("selection: claim-by-rename survives a racing write", check_selection_claim_is_atomic_rename()),
        ("shim + selection: round trip, then clears", check_shim_round_trip()),
    ]
    ok = all(v for _, v in checks)
    for name, v in checks:
        print(f"  {'PASS' if v else 'FAIL'}  {name}")
    print(f"\nplan-pane smoke: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
