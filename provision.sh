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

# Pi local-model endpoints: symlink the repo's SSOT models.json into pi's config
# so edits propagate live (same philosophy as AGENTS.md). Bring the servers up
# with bin/local-models up.
PI_MODELS="$(dirname "$SSOT")/orchestration/pi-models.json"
if [ -f "$PI_MODELS" ]; then
  mkdir -p "$HOME/.pi/agent"
  ln -sf "$PI_MODELS" "$HOME/.pi/agent/models.json"
  echo "linked $HOME/.pi/agent/models.json -> $PI_MODELS"
fi

# Claude Code only reads CLAUDE.md -> ensure the @import line, without clobbering.
mkdir -p "$HOME/.claude"
touch "$HOME/.claude/CLAUDE.md"
grep -qxF "@$SSOT" "$HOME/.claude/CLAUDE.md" || printf '@%s\n' "$SSOT" >> "$HOME/.claude/CLAUDE.md"
echo "ensured @import in $HOME/.claude/CLAUDE.md"

# orbal-net: one Rust binary (github.com/zico-io/orbal-net) that is both the
# per-mission server (`orbal-net serve`) and the client agents call. Install it
# for the host and put it on the orchestrator's PATH. spawn.py's
# `_ensure_orbal_net` does the same check-and-install at mission-up time, so
# this is a convenience: front-load the (slow, network) install here instead
# of on the first `spawn.py up`.
if command -v cargo >/dev/null 2>&1; then
  if command -v orbal-net >/dev/null 2>&1; then
    echo "orbal-net already on PATH"
  elif cargo install --quiet orbal-net || cargo install --quiet --git https://github.com/zico-io/orbal-net orbal-net; then
    echo "installed orbal-net -> $(command -v orbal-net)"
  else
    echo "orbal-net install FAILED (tried crates.io and git)." >&2
    echo "This is fatal: agents reach the mission server via this binary, and a" >&2
    echo "missing image binary makes them recompile it from the mission repo at join." >&2
    exit 1
  fi
else
  echo "note: cargo not found — install Rust (https://rustup.rs) to install the orbal-net binary"
fi
