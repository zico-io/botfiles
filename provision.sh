#!/usr/bin/env bash
# provision.sh — wire this repo into every harness's global config.
# Idempotent: re-run any time. Symlinks so edits here propagate live.
set -euo pipefail

SSOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/AGENTS.md"
[ -f "$SSOT" ] || { echo "missing $SSOT" >&2; exit 1; }
ROOT="$(dirname "$SSOT")"
# The old ~/.botfiles layout made ~/.pi itself a symlink; writing through it would
# land in that repo. Move pi's runtime (auth.json, sessions/, npm/, ...) into a
# real ~/.pi first.
[ -L "$HOME/.pi" ] && { echo "$HOME/.pi is a symlink; make it a real dir first" >&2; exit 1; }

# Claude Code, Codex, and Pi read AGENTS.md natively -> symlink straight to the SSOT.
for dir in "$HOME/.claude" "$HOME/.codex" "$HOME/.pi/agent"; do
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

# Harness config (claude/, pi/, config/, launchd/): link each piece into place.
# An existing real file or dir is moved to .bak instead of clobbered; ln -sfn
# replaces an old link instead of nesting inside it. A missing source (the
# sandbox image ships only AGENTS.md, skills/, and this script) is skipped.
link() {
  [ -e "$1" ] || return 0
  mkdir -p "$(dirname "$2")"
  if [ -e "$2" ] && [ ! -L "$2" ]; then mv "$2" "$2.bak" && echo "backed up $2 -> $2.bak"; fi
  ln -sfn "$1" "$2"
  echo "linked $2 -> $1"
}
for d in agents commands hooks; do link "$ROOT/claude/$d" "$HOME/.claude/$d"; done
for f in agents extensions prompts settings.json; do link "$ROOT/pi/agent/$f" "$HOME/.pi/agent/$f"; done
link "$ROOT/pi/missions" "$HOME/.pi/missions"
link "$ROOT/config/herdr/config.toml" "$HOME/.config/herdr/config.toml"
# Extension deps are not committed; install any that are missing.
if command -v npm >/dev/null 2>&1; then
  for pkg in "$ROOT"/pi/agent/extensions/*/package.json; do
    [ -f "$pkg" ] || continue
    d="$(dirname "$pkg")"
    if grep -q '"dependencies"' "$pkg" && [ ! -d "$d/node_modules" ]; then
      (cd "$d" && npm install --no-audit --no-fund --silent) && echo "installed deps in $d"
    fi
  done
fi
if [ "$(uname)" = Darwin ]; then
  for plist in "$ROOT"/launchd/*.plist; do
    [ -f "$plist" ] || continue
    dest="$HOME/Library/LaunchAgents/$(basename "$plist")"
    link "$plist" "$dest"
    launchctl bootout "gui/$(id -u)" "$dest" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$dest" && echo "loaded $(basename "$plist" .plist)"
  done
fi

# skills/: served through the toolbox MCP server (bin/toolbox, which indexes
# skills/ via toolbox/catalog.json) so they cost no context until searched.
# Claude Code and Codex get the server registered; a harness that cannot reach
# it (pi has no MCP client, or the sandbox image, which ships no bin/toolbox)
# gets each skill symlinked into its skills dir instead (ln -sfn replaces the
# link instead of nesting on re-run). A harness switched to the toolbox has its
# old links removed so no skill loads twice.
TOOLBOX="$ROOT/bin/toolbox"
for pair in "claude:$HOME/.claude/skills" "codex:$HOME/.codex/skills" "pi:$HOME/.pi/agent/skills"; do
  cli="${pair%%:*}" harness_dir="${pair#*:}"
  served=
  if [ "$cli" != pi ] && [ -x "$TOOLBOX" ] && command -v "$cli" >/dev/null 2>&1; then
    if [ "$cli" = claude ]; then add=(claude mcp add -s user); else add=(codex mcp add); fi
    "$cli" mcp get toolbox >/dev/null 2>&1 || "${add[@]}" toolbox -- "$TOOLBOX" mcp >/dev/null
    echo "registered toolbox MCP server in $cli"
    served=1
  fi
  mkdir -p "$harness_dir"
  for skill in "$ROOT"/skills/*/SKILL.md; do
    [ -f "$skill" ] || continue
    src="$(dirname "$skill")" link="$harness_dir/$(basename "$(dirname "$skill")")"
    if [ -n "$served" ]; then
      [ "$(readlink "$link")" = "$src" ] && rm "$link" && echo "unlinked $link (served by toolbox)"
    else
      ln -sfn "$src" "$link"
      echo "linked $link -> $src"
    fi
  done
done

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
