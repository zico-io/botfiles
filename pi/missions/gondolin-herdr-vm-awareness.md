# Mission: Gondolin Proxy Mode — Herdr Pane VM Awareness

## Goal

When gondolin is active, any herdr pane launched by pi runs inside the same VM context — not on the raw host.

## Current state

- pi runs on host, gondolin proxies tools through a VM at `/workspace`
- No env flag, so review/subagent extensions don't know gondolin is active
- Review runs `herdr pane run <pane> "glow /workspace/file.md"` — path is in VM space, glow runs on host, fails
- Subagent spawns pi processes — may or may not load gondolin

## Changes

### 1. Gondolin extension — export proxy state

- Set `GONDOLIN_VM=1` env var on the pi process (subprocesses inherit it)
- Set `GONDOLIN_HOST_CWD=<host-cwd>` env var for path mapping
- Guest path `/workspace/foo` maps to host `<GONDOLIN_HOST_CWD>/foo`

### 2. Review extension — VM-aware paths

- When `GONDOLIN_VM=1`, map guest paths to host paths before running herdr pane commands
- `glow '/workspace/foo.md'` → `glow '<host-cwd>/foo.md'`

### 3. Subagent extension — VM-aware spawns

- Audit: do subagent pi processes inherit gondolin extension loading?
- If not: ensure they do when `GONDOLIN_VM=1`

## Squad assignments

| Step | Agent | Task |
|------|-------|------|
| 1 | Worker | Add env vars + hostToGuest helper to gondolin extension |
| 2 | Worker | Add VM-aware path mapping to review extension |
| 3 | Worker | Audit/fix subagent extension for VM compatibility |
| 4 | Reviewer | Review all changes |

## Sequence

Scout (understand gondolin fully) → Build (parallel) → Review
