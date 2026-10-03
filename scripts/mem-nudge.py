#!/usr/bin/env python3
"""Stop hook: nudge to synthesize memories after a subagent session that saved none.

Mirrors the pi memweave `agent_end` behavior. Reads Claude Code Stop-hook JSON on
stdin; blocks the stop once (with a synthesis nudge) if the session used subagents
but never wrote a memory. `stop_hook_active` guards against re-firing in a loop.
"""

import json
import pathlib
import sys

data = json.load(sys.stdin)

# already nudged this stop — let it end (no loop)
if data.get("stop_hook_active"):
    sys.exit(0)

tp = data.get("transcript_path")
if not tp or not pathlib.Path(tp).exists():
    sys.exit(0)

text = pathlib.Path(tp).read_text(encoding="utf-8", errors="ignore")

used_subagents = '"Task"' in text or '"Agent"' in text
wrote_memory = "mem.py write" in text or "mem_write" in text

if used_subagents and not wrote_memory:
    print(
        json.dumps(
            {
                "decision": "block",
                "reason": (
                    "This session used subagents but saved no memory. Recall related "
                    "memories with `python3 scripts/mem.py search`, then persist any "
                    "durable facts/decisions with `python3 scripts/mem.py write <slug> "
                    '"..."`. If nothing is worth remembering, say so and stop.'
                ),
            }
        )
    )
sys.exit(0)
