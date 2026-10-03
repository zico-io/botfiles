---
disable-model-invocation: true
description: Research ticket and launch planning session
---

1. use SlashCommand() to call /ralph_research with the given ticket number
2. launch a new session with `claude --model opus --dangerously-skip-permissions --verbose "/oneshot_plan ENG-XXXX"`
