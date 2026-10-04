# Toolbox

`bin/toolbox` exposes skills and MCP integrations through two tools:

- `search(query)` - BM25 over names and descriptions, returns ranked tool names.
- `use(tool, prompt)` - a **skill** returns its SKILL.md body for the caller to
  follow. An **integration** runs `prompt` in a `claude -p` subagent that sees
  only that server's tools and returns the result.

`toolbox/catalog.json` lists skill roots (relative to the catalog), Claude plugins to index,
and MCP integrations. An integration is a normal MCP server config (`http`,
`stdio`, `sse`) plus a `description`, or `"type": "claudeai"` for a claude.ai
connector, named as it appears in tool ids (`Google_Calendar`). Descriptions
drive search, so name the nouns and verbs an agent would ask for.

```bash
bin/toolbox search "why is my deploy failing"
bin/toolbox use Notion "find the onboarding page and summarise it"
bash provision.sh   # registers toolbox in Claude Code and Codex
```

Run these commands from the repository root. Integration calls require the
Claude CLI and authentication for the selected server.

To take something out of ambient context, add it to the catalog, then hide it
from the main session: `permissions.deny: ["mcp__<server>"]` in
`~/.claude/settings.json` for an MCP server, or disable the plugin. The subagent
runs with `--setting-sources project` from an empty temp dir, so it skips those
denies (and user hooks and plugins) and can still reach the server. It reuses the
harness's stored OAuth, so authorise a server once in an interactive `/mcp`.

A `use` call has the integration's full tool surface, writes included, gated
only by the caller's approval of the `use` call itself. `$TOOLBOX_MODEL`
(default `claude-sonnet-5-5`) picks the subagent model.

[Back to the README](../README.md)
