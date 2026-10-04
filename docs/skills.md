# Shared Linear skills

The canonical skill source is `Bask-Health/skills`:

- `build/create-issue` selects Linear or GitHub.
- `build/issue-intake` owns the shared Linear workflow and runtime adapters.
- `build/linear-issue` remains the separate read/analyze skill.

The fleet uses `@repo/issues/intake` and `@repo/linear` in `Bask-Health/bots`
for deterministic filing. Direct Linear tools in T3 use the terminal adapter;
that adapter reports unavailable fleet assessment, ledger and customer-need
features instead of claiming full runtime parity.

## Edit locally

Clone the source on the T3 server and edit its skill files. For immediate local
iteration, point the toolbox at its category directories with
`BASK_SKILLS_ROOT=/path/to/skills`. The toolbox searches that checkout before
packaged copies, so changes are available on the next search/use call. Set this
variable when running `bash provision.sh` or `botfiles-provision`; it is saved
in each provider's toolbox server configuration. Re-run provisioning without the
variable to return to packaged skills.

## Sync deployable copies

Run from botfiles, substituting your checkout paths:

```bash
./bin/sync-skills --source /path/to/skills --layout botfiles
./bin/sync-skills --source /path/to/skills --target /path/to/bots --layout bots
./bin/sync-skills --check --source /path/to/skills
python3 /path/to/bots/scripts/sync-linear-skills.py --check --source /path/to/skills
```

The sync writes skill copies and `linear-skills.lock.json`, which records the
source revision, whether the source checkout has local changes, and SHA-256
checksums. Do not edit those generated files. Local edits can be synced for
review; release copies should come from a committed source revision. CI checks
that copies match their lockfile without requiring cross-repository credentials.
Passing `--source` also checks them against the current source checkout.

Review and commit the source and generated consumer changes together. Rebuild
the T3 host to deploy botfiles. The bots copy is the shared issues extension's
intake skill; build and deploy its consuming agents, including Bob and Herald,
through the normal bots workflow. Syncing files does not deploy or restart live agents.
The fleet adapter preserves the existing `issues__file` filing authority.

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
