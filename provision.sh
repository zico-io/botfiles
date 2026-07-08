#!/usr/bin/env bash
# provision.sh — wire this .botfiles SSOT into every harness's global config.
# Idempotent: re-run any time. Symlinks so edits to AGENTS.md propagate live.
set -euo pipefail

SSOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/AGENTS.md"
[ -f "$SSOT" ] || { echo "missing $SSOT" >&2; exit 1; }

# Codex + Pi read AGENTS.md natively -> symlink straight to the SSOT.
for dir in "$HOME/.codex" "$HOME/.pi/agent"; do
  mkdir -p "$dir"
  ln -sf "$SSOT" "$dir/AGENTS.md"
  echo "linked $dir/AGENTS.md -> $SSOT"
done

# Claude Code only reads CLAUDE.md -> ensure the @import line, without clobbering.
mkdir -p "$HOME/.claude"
touch "$HOME/.claude/CLAUDE.md"
grep -qxF "@$SSOT" "$HOME/.claude/CLAUDE.md" || printf '@%s\n' "$SSOT" >> "$HOME/.claude/CLAUDE.md"
echo "ensured @import in $HOME/.claude/CLAUDE.md"

# agent-comms: give each harness the cross-harness A2A mesh used by the
# orchestration harness (see orchestration/). Claude is wired via `claude mcp`
# already; here we ensure codex and pi. Idempotent.

# Codex reads MCP servers from config.toml; it uses the `codex` bridge.
CODEX_CFG="$HOME/.codex/config.toml"
touch "$CODEX_CFG"
if grep -q '^\[mcp_servers.agent-comms\]' "$CODEX_CFG"; then
  echo "agent-comms mcp already in $CODEX_CFG"
else
  cat >> "$CODEX_CFG" <<'TOML'

[mcp_servers.agent-comms]
command = "npx"
args = ["agent-comms", "bridge", "codex"]
TOML
  echo "added agent-comms mcp to $CODEX_CFG"
fi

# Pi loads agent-comms as an npm package (no bridge id).
PI_CFG="$HOME/.pi/agent/settings.json"
python3 - "$PI_CFG" <<'PY'
import json, os, sys
p = sys.argv[1]
cfg = json.load(open(p)) if os.path.exists(p) and os.path.getsize(p) else {}
pkgs = cfg.setdefault("packages", [])
if "npm:agent-comms" in pkgs:
    print(f"npm:agent-comms already in {p}")
else:
    pkgs.append("npm:agent-comms")
    json.dump(cfg, open(p, "w"), indent=2)
    print(f"added npm:agent-comms to {p}")
PY
