# tools/orchestration — multi-agent harness

- Fleets run on herdr (panes/tabs/status) + the agent-comms tool (rooms/DMs);
  herdr does placement and process, agent-comms does coordination. <source: orchestration/spawn.py, 2026-07-07>
- Hierarchy is capped at 3 layers, enforced by room membership: L1 orchestrator + L2 leads share `mission-<feature>`; each L2 lead + its L3 workers share `squad-<lead>`; the orchestrator never shares a room with a worker. <source: AGENTS.md orchestration protocol, 2026-07-07>
- `orchestration/spawn.py up <roster.json>` spawns the fleet (leads as tabs, workers as splits), launches each harness, and injects a bootstrap that registers the agent into agent-comms; `down <feature>` closes the workspace. Rooms are torn down by the orchestrator via agent-comms `destroy_room`. <source: orchestration/spawn.py, 2026-07-07>
- Supported harnesses: claude, codex, pi (launch templates in the `HARNESSES` map). Cross-harness comms requires the agent-comms wiring that `provision.sh` ensures: codex via `[mcp_servers.agent-comms]` (bridge `codex`), pi via the `npm:agent-comms` package, claude via `claude mcp` (bridge `claude-code`). There is no `pi` bridge. <source: provision.sh + `agent-comms bridge`, 2026-07-07>
- Roster schema and the orchestrator drive loop: `orchestration/roster.example.json`, `.claude/commands/spawn-team.md`. Modeled on github.com/disler/learning-cmux-with-agents (cmux → herdr, screen-scraping → agent-comms). <source: orchestration/, 2026-07-07>
