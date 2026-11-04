# forge

`forge push` ships a branch through one command. It runs the repo's quality
gates cheapest first, stops at the first failure, and pushes only when they all
pass. Agents call it instead of `git push`.

```bash
forge push                     # gates, then push
forge push --check             # gates only
forge push --base develop      # compare against another base branch
forge push --skip unit --reason "fails on main too, see #123"
./bin/forge selfcheck          # end-to-end run against a fixture repo and a fake devenv
```

It prints one JSON object. `status` is `pushed`, `checked`, `blocked` or
`error`, with exit code 0, 0, 1 or 2. `gates` holds each gate's `status`,
`duration_s` and up to 20 `findings`. `log_dir` holds the full logs, under
`~/.cache/forge/logs/`. `next` is one line telling the agent what to do.

## Gates

| Step | Limit | What runs |
| --- | --- | --- |
| preflight | rest of budget | clean tree, `git fetch origin <base>`, merge base, `devenv up -d`, `devenv processes wait`, `devenv tasks run forge:ready` |
| cache | | skip to push if this tree, merge base and devenv config already passed |
| format | 60 s | `forge:format` |
| lint | 60 s | `forge:lint` |
| autofix | | edits from format and lint are committed as `style: forge autofix` |
| typecheck | 300 s | `forge:typecheck` |
| unit | 300 s | `forge:unit` |
| integration | 300 s | `forge:integration` |
| push | | `git push origin <branch>`, with `-u` when there is no upstream, never forced |

The whole run has 840 s, preflight included, which keeps it under the
toolbox's 900 s limit. A timeout blocks.

The gate commands live in the repo's `devenv.nix`, so forge knows no repo
tooling. The [forge-env skill](../skills/forge-env/SKILL.md) writes that file
and defines the task contract. It covers the `FORGE_MERGE_BASE`,
`FORGE_BASE` and `FORGE_CHANGED_FILES` variables, exit codes and output. Set
`env.FORGE_BASE` there to change the default base branch, which otherwise is
origin's HEAD branch.

## Behaviour worth knowing

- **Cache.** The key is the tree SHA, the merge base, the skip list, and the
  contents of `devenv.nix`, `devenv.lock`, `devenv.yaml` and `bin/forge`. A run
  with `--skip` is never cached. Entries live in `~/.cache/forge/pass/`.
- **Services.** forge stops the processes it started on every exit path,
  including failures, timeouts and SIGTERM. If services were already running
  when it started, it leaves them running.
- **Pre-existing failures** are not detected. A gate that also fails on the
  base branch still blocks. Skip it with `--skip <gate> --reason`. The reason
  is in the `ponytail:` note in `bin/forge`.
- **devenv 2.1.2.** `devenv tasks run` deletes a running process manager's
  pid file and socket, so `devenv processes down` stops working after the
  first gate. forge records the manager's pid after `devenv up -d` and
  signals it directly at teardown. forge also sets `DEVENV_NO_AI_AGENT=1`,
  because devenv's agent auto-quiet drops task stdout.

## Push guard

`hooks/forge-push-guard.py` is a Claude Code PreToolUse hook. It denies a bare
`git push` with "use `forge push`". It is a guardrail, not a wall:
`git -C dir push` and `command git push` pass on purpose, and forge pushes
through a subprocess the hook never sees. `./bin/botfile wire --tool claude`
registers it in `~/.claude/settings.json`. `wire` also links
`~/.local/bin/forge` to this checkout. `bash provision.sh` runs both.

[Back to the README](../README.md)
