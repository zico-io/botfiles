#!/bin/sh
# entrypoint — inject per-mission harness credentials mounted read-only at
# /secrets into HOME, then run the container command (sleep infinity). Harnesses
# are attached later via `container exec`, inheriting this provisioned HOME.
set -e

if [ -f /secrets/claude.credentials.json ]; then
  mkdir -p "$HOME/.claude"
  cp /secrets/claude.credentials.json "$HOME/.claude/.credentials.json"
  chmod 600 "$HOME/.claude/.credentials.json"
fi

if [ -f /secrets/codex.auth.json ]; then
  mkdir -p "$HOME/.codex"
  cp /secrets/codex.auth.json "$HOME/.codex/auth.json"
  chmod 600 "$HOME/.codex/auth.json"
fi

if [ -f /secrets/vercel.auth.json ]; then
  mkdir -p "$HOME/.local/share/com.vercel.cli"
  cp /secrets/vercel.auth.json "$HOME/.local/share/com.vercel.cli/auth.json"
  chmod 600 "$HOME/.local/share/com.vercel.cli/auth.json"
fi

exec "$@"
