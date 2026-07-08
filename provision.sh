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

# comms: one Rust binary that is both the per-mission server (`comms serve`) and the
# client agents call. Build it for the host and put it on the orchestrator's PATH.
# (In the image build this source tree is absent; the Containerfile builds the guest
# binary in a multi-stage step instead, so the guard keeps the image build clean.)
COMMS_DIR="$(dirname "$SSOT")/comms"
if [ -d "$COMMS_DIR" ]; then
  if command -v cargo >/dev/null 2>&1; then
    ( cd "$COMMS_DIR" && cargo build --release --quiet ) \
      && ln -sf "$COMMS_DIR/target/release/comms" /usr/local/bin/comms 2>/dev/null \
      && echo "built + linked /usr/local/bin/comms -> $COMMS_DIR/target/release/comms" \
      || echo "note: comms build/symlink failed (add $COMMS_DIR/target/release to PATH manually)"
  else
    echo "note: cargo not found — install Rust (https://rustup.rs) to build the comms binary"
  fi
fi
