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

# comms client: agent coordination is now the per-mission host comms server
# (orchestration/comms_server.py), reached with the stdlib `comms` CLI over TCP -
# no MCP server, no in-guest daemon. Put `comms` on the host orchestrator's PATH.
# (In the image build this source path is absent; the Containerfile COPYs the
# client into the guest instead, so the guard keeps the build clean.)
COMMS_SRC="$(dirname "$SSOT")/bin/comms"
if [ -f "$COMMS_SRC" ]; then
  ln -sf "$COMMS_SRC" /usr/local/bin/comms 2>/dev/null \
    && echo "linked /usr/local/bin/comms -> $COMMS_SRC" \
    || echo "note: could not symlink comms into /usr/local/bin (add $COMMS_SRC to PATH manually)"
fi
