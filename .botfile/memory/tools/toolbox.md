# toolbox - search/use front door for skills and MCP integrations

- `bin/toolbox` exposes two MCP tools, `search(query)` and `use(tool, prompt)`, so skills and MCP servers live in `toolbox/catalog.json` instead of ambient context <source: toolbox build session, 2026-09-29>
- `use` on an integration runs `claude -p` from an empty temp dir with `--setting-sources project`, `--tools ToolSearch`, `--allowedTools mcp__<server>`, plus `--strict-mcp-config --mcp-config` for non-claude.ai servers; user-settings deny rules do not apply there, so a server denied in the main session stays reachable <source: toolbox build session, 2026-09-29>
- claude.ai connectors race `claude -p` startup and are often missing on turn one; `MCP_CONNECTION_NONBLOCKING=0` makes the run wait for them (3/3 vs 2/3 without) <source: toolbox build session, 2026-09-29>
- `--tools ""` hides MCP tools entirely because deferred MCP tools are reached through ToolSearch; keep `ToolSearch` in the subagent's tool list <source: toolbox build session, 2026-09-29>
- An http MCP server's OAuth token is reused by the subagent when the server name and url match the harness config; authorise once in interactive `/mcp` <source: toolbox build session, 2026-09-29>
- `--system-prompt` drops Claude Code's date line, so the runner prompt injects the current local time; without it calendar queries anchored on midnight <source: toolbox build session, 2026-09-29>
- Harness-specific skill roots (`~/.agents/skills`, `~/.codex/skills`) are left out of the catalog: they hold Cursor/Codex-only skills and `source-command-*` copies of Claude commands <source: toolbox build session, 2026-09-29>

- Shared Linear creation skills come from `Bask-Health/skills/build/{create-issue,issue-intake}`; `bin/sync-skills` generates deployable copies and a checksum lockfile. `BASK_SKILLS_ROOT` searches a local source checkout first for immediate iteration. Fleet writes remain in `Bask-Health/bots` packages `issues` and `linear`. <source: user consolidation request, bin/toolbox and docs/skills.md, 2026-10-04>
