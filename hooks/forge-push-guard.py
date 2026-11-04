#!/usr/bin/env python3
"""Claude Code PreToolUse hook (Bash): deny a bare `git push`, point at `forge push`.

A guardrail, not a wall. It matches `git push` only where a command starts
(line start, or after ; & | ( ), so `git -C dir push`, `command git push` and
`forge push` itself (which pushes through a subprocess, not the Bash tool) pass.
Those bypasses are deliberate: a repo without devenv.nix, or a human-approved
force push, still needs a way out.
"""
import json
import re
import sys

BARE_PUSH = re.compile(r"(?:^|[;&|(\n])\s*git\s+push\b")


def decide(command):
    if not BARE_PUSH.search(command):
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "use `forge push`",
        }
    }


if __name__ == "__main__":
    try:
        command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    except (json.JSONDecodeError, AttributeError):
        sys.exit(0)
    verdict = decide(command)
    if verdict:
        print(json.dumps(verdict))
