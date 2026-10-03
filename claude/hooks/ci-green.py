#!/usr/bin/env python3
"""Stop hook: in T3 Code, keep the agent working until its PR's CI is green.

Only fires when this session pushed or opened a PR. Does not block on:
  - checks that also fail on the base branch (already broken, not ours)
  - checks whose name matches a regex in ~/.claude/ci-flaky or <repo>/.claude/ci-flaky
Gives up after MAX_BLOCKS nudges per session so an unfixable failure can't loop forever.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_BLOCKS = 10
FAILED = {"failure", "timed_out", "startup_failure", "error"}


def gh(*args, cwd):
    r = subprocess.run(["gh", *args], cwd=cwd, capture_output=True, text=True, timeout=30)
    return r.stdout if r.stdout.strip() else None


def session_pushed(transcript_path):
    try:
        lines = Path(transcript_path).read_text().splitlines()
    except OSError:
        return False
    for line in lines:
        try:
            content = json.loads(line).get("message", {}).get("content")
        except (json.JSONDecodeError, AttributeError):
            continue
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                cmd = str(block.get("input", {}).get("command", ""))
                if re.search(r"\bgit\s+push\b|\bgh\s+pr\s+create\b", cmd):
                    return True
    return False


def flaky_patterns(cwd):
    pats = []
    for f in (Path.home() / ".claude/ci-flaky", Path(cwd) / ".claude/ci-flaky"):
        if f.is_file():
            pats += [l.strip() for l in f.read_text().splitlines() if l.strip() and not l.startswith("#")]
    return pats


def base_failures(base, cwd):
    runs = gh("api", f"repos/{{owner}}/{{repo}}/commits/{base}/check-runs?per_page=100",
              "--jq", ".check_runs[] | [.name, .conclusion] | @tsv", cwd=cwd) or ""
    statuses = gh("api", f"repos/{{owner}}/{{repo}}/commits/{base}/status",
                  "--jq", ".statuses[] | [.context, .state] | @tsv", cwd=cwd) or ""
    rows = [l.split("\t") for l in (runs + statuses).splitlines() if "\t" in l]
    return {name for name, state in rows if state in FAILED}


def classify(checks, base_failed, flaky):
    """Returns (failing, pending, ignored) check-name lists."""
    failing, pending, ignored = [], [], []
    for c in checks:
        name, bucket = c["name"], c["bucket"]
        if bucket not in ("fail", "pending", "cancel"):
            continue
        if name in base_failed or any(re.search(p, name) for p in flaky):
            ignored.append(name)
        elif bucket == "pending":
            pending.append(name)
        else:
            failing.append(name)
    return failing, pending, ignored


def main():
    if os.environ.get("__CFBundleIdentifier") != "com.t3tools.t3code":
        return
    event = json.load(sys.stdin)
    cwd = event.get("cwd") or os.getcwd()
    if not session_pushed(event.get("transcript_path", "")):
        return
    pr = gh("pr", "view", "--json", "number,state,baseRefName,url", cwd=cwd)
    if not pr or json.loads(pr)["state"] != "OPEN":
        return
    pr = json.loads(pr)
    checks = json.loads(gh("pr", "checks", str(pr["number"]), "--json", "name,bucket", cwd=cwd) or "[]")
    failing, pending, ignored = classify(checks, base_failures(pr["baseRefName"], cwd), flaky_patterns(cwd))
    if not failing and not pending:
        return

    counter = Path(tempfile.gettempdir()) / "claude-ci-green" / event.get("session_id", "unknown")
    counter.parent.mkdir(exist_ok=True)
    count = int(counter.read_text()) if counter.exists() else 0
    if count >= MAX_BLOCKS:
        return
    counter.write_text(str(count + 1))

    n = pr["number"]
    parts = [f"CI for PR #{n} ({pr['url']}) is not green yet (nudge {count + 1}/{MAX_BLOCKS})."]
    if failing:
        parts.append(f"Failing: {', '.join(failing)}. Fetch logs with `gh run view <run-id> --log-failed`, "
                     "reproduce locally, fix the root cause, push, then watch again.")
    if pending:
        parts.append(f"Pending: {', '.join(pending)}. Wait with `gh pr checks {n} --watch --fail-fast` "
                     "(Bash timeout 600000) and handle the result.")
    if ignored:
        parts.append(f"Ignored as known bad/flaky: {', '.join(ignored)}.")
    parts.append("If a failure is outside your control, say so with the log excerpt and add its name "
                 "to .claude/ci-flaky only if it is genuinely flaky.")
    print(json.dumps({"decision": "block", "reason": " ".join(parts)}))


def selftest():
    checks = [{"name": "lint", "bucket": "fail"}, {"name": "e2e (chrome)", "bucket": "fail"},
              {"name": "deploy", "bucket": "fail"}, {"name": "build", "bucket": "pending"},
              {"name": "unit", "bucket": "pass"}, {"name": "docs", "bucket": "skipping"}]
    assert classify(checks, {"deploy"}, [r"^e2e"]) == (["lint"], ["build"], ["e2e (chrome)", "deploy"])
    assert classify([{"name": "unit", "bucket": "pass"}], set(), []) == ([], [], [])
    print("ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        try:
            main()
        except Exception as e:  # never wedge the session on a gh/network hiccup
            print(f"ci-green: {e}", file=sys.stderr)
