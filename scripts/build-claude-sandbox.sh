#!/usr/bin/env bash
# One-time: install Claude Code into a persistent host dir that the sandbox mounts.
# node is already in the gondolin base image; only claude-code needs installing, and
# it goes on the host (the guest rootfs has ~85M free) so no snapshot/resize is needed.
# Re-run this to update the sandboxed claude-code version.
set -euo pipefail
export PATH="/opt/homebrew/bin:$PATH"   # qemu etc. — launchd runs with a minimal PATH
NODE=/opt/homebrew/opt/node@26/bin/node
GONDOLIN="$HOME/.pi/agent/extensions/gondolin/node_modules/.bin/gondolin"
PREFIX="$HOME/.cache/claude-sandbox"

mkdir -p "$PREFIX"
exec "$NODE" "$GONDOLIN" bash --dns open \
  --mount-hostfs "$PREFIX:/opt/claude" \
  -- sh -lc 'CI=1 npm install --prefix /opt/claude -g @anthropic-ai/claude-code --no-progress --no-fund --no-audit && /opt/claude/bin/claude --version'
