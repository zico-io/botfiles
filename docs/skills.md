# Shared Linear skills

The canonical skill source is `Bask-Health/skills`:

- `build/create-issue` selects Linear or GitHub.
- `build/issue-intake` owns the shared Linear workflow and runtime adapters.
- `build/linear-issue` remains the separate read/analyze skill.

The fleet uses `@repo/issues/intake` and `@repo/linear` in `Bask-Health/bots`
for deterministic filing. Direct Linear tools in T3 use the terminal adapter;
that adapter reports unavailable fleet assessment, ledger and customer-need
features instead of claiming full runtime parity.

## Where the server gets them

Skills are authored once in `Bask-Health/skills` and never copied here. On
sandbox-host the `bask-skills` user timer clones that repo into
`~/.local/share/bask-skills` and fast-forwards it every 15 minutes, using the
login's `gh auth`. The toolbox reads its `build/`, `content/` and `research/`
directories ahead of everything else, so a merge to `main` is live on the
next pull, with no botfiles change or rebuild. Check it with
`systemctl --user status bask-skills`.

The fleet does the same at build time: `Bask-Health/bots` fetches the intake
skill from `main` on install, so its next deploy carries the change.

## Edit locally

Point the toolbox at your working checkout with
`BASK_SKILLS_ROOT=/path/to/skills` when running `bash provision.sh` or
`botfiles-provision`; it is saved in each provider's toolbox server config and
takes effect on the next search/use call. Re-run provisioning without the
variable to return to the pulled clone.

## Linear authentication

The toolbox catalog includes `linear`, using Linear's [official MCP server](https://linear.app/docs/mcp).
For toolbox integration calls, register that same name and endpoint in Claude
once as the server user, then authenticate through its interactive `/mcp`:

```bash
claude mcp add -s user --transport http linear https://mcp.linear.app/mcp
```

The toolbox runner reuses that connection's OAuth. If Linear tools are already
connected directly in the provider, the terminal adapter can use them there.
Neither skill sync nor a host rebuild authenticates a Linear account.
