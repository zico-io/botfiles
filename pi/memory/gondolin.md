# Gondolin VM Conventions

## How Gondolin Works
- The host cwd (the pi workspace) is mounted at `/workspace` inside the VM
- `GONDOLIN_VM=1` signals we're inside the sandbox
- `GONDOLIN_HOST_CWD` holds the host path equivalent of `/workspace`
- Node.js `spawn`/`exec` inherits parent env automatically — no explicit `env` needed

## Patterns for Gondolin Compatibility
- **CWD translation**: When spawning child processes from a gondolin VM, translate `/workspace` → `GONDOLIN_HOST_CWD` so the child gets a valid host path
- **Extension loading**: Child `pi` processes inside gondolin need `-e ~/.pi/agent/extensions/gondolin` to load filesystem translation etc.
- **Env forwarding**: `GONDOLIN_VM`, `GONDOLIN_HOST_CWD`, and other gondolin env vars propagate automatically via process inheritance
- **File access**: Inside the VM, host paths like `/Users/percules/...` are NOT accessible; use `/workspace/...` (guest) or translate

## Files Modified for Gondolin
- `/Users/percules/.pi/agent/extensions/subagent/index.ts` — subagent spawn cwd translation + extension loading (2026-07-11)
