#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLBOX="${BOTFILES_TOOLBOX:-$ROOT/bin/toolbox}"
"$ROOT/bin/botfile" wire --tool all

for cli in claude codex; do
  if ! command -v "$cli" >/dev/null 2>&1; then
    echo "note: $cli not installed; instructions are wired"
    continue
  fi
  config=$("$cli" mcp get toolbox 2>/dev/null || true)
  if [[ "$config" != *"$TOOLBOX"* ]] || [[ -n "${BASK_SKILLS_ROOT:-}" && "$config" != *"$BASK_SKILLS_ROOT"* ]] || [[ -z "${BASK_SKILLS_ROOT:-}" && "$config" == *BASK_SKILLS_ROOT* ]]; then
    if [ "$cli" = claude ]; then
      claude mcp remove -s user toolbox >/dev/null 2>&1 || true
      env_args=()
      if [ -n "${BASK_SKILLS_ROOT:-}" ]; then
        env_args=(-e "BASK_SKILLS_ROOT=$BASK_SKILLS_ROOT")
      fi
      claude mcp add -s user toolbox "${env_args[@]}" -- "$TOOLBOX" mcp
    else
      codex mcp remove toolbox >/dev/null 2>&1 || true
      env_args=()
      if [ -n "${BASK_SKILLS_ROOT:-}" ]; then
        env_args=(--env "BASK_SKILLS_ROOT=$BASK_SKILLS_ROOT")
      fi
      codex mcp add toolbox "${env_args[@]}" -- "$TOOLBOX" mcp
    fi
  fi
  echo "toolbox registered in $cli"
done
