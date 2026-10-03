# Gondolin Subagent Compatibility Fix (2026-07-11)

## Context
Pi subagent extension spawns child `pi` processes for delegated tasks. Under Gondolin VM, these child processes need host-aware paths and the gondolin extension loaded.

## Changes Made
Two targeted additions to `/Users/percules/.pi/agent/extensions/subagent/index.ts` in `runSingleAgent`:

1. **CWD translation** (line ~340-345): When `GONDOLIN_VM=1` and cwd starts with `/workspace`, translates to host path via `GONDOLIN_HOST_CWD`. Applied just before the `spawn()` call.

2. **Gondolin extension loading** (line ~298-301): When `GONDOLIN_VM=1`, adds `-e ~/.pi/agent/extensions/gondolin` to pi args so subagents load the gondolin extension (filesystem translation, env forwarding).

## Key Insight
Node.js `spawn` inherits parent env automatically, so `GONDOLIN_VM=1` and `GONDOLIN_HOST_CWD` propagate without explicit `env` passing. Only cwd and extension args needed fixing.
