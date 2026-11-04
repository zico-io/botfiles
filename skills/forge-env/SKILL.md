---
name: forge-env
description: "Write devenv.nix and devenv.yaml for a pnpm monorepo so `forge push` can run its gates: Node and pnpm toolchain, test services (MySQL, ClickHouse, fakes such as Stripe), per-worktree ports, setup tasks (install, codegen, migrate, seed, ready) and the forge:format, forge:lint, forge:typecheck, forge:unit and forge:integration gate tasks. Use when `forge push` reports no devenv.nix, when a forge gate task is missing or wrong, or when the user asks to set up devenv, a dev environment, or forge for a repo. Not for running the gates (use `forge push`)."
license: MIT
metadata:
  author: botfiles
  version: '1.0'
---

# forge-env

`forge push` hardcodes no repo tooling. Every command it runs is a devenv task
in the repo's `devenv.nix`. This skill introspects the repo and writes that
file, then proves it works. Target devenv 2.1.2 or later (`devenv version`).

## 1. Introspect

Read these before writing anything:

| Source | Gives you |
| --- | --- |
| `.nvmrc`, `package.json` `engines` and `packageManager` | Node major, pnpm version |
| `pnpm-workspace.yaml`, `turbo.json` | packages, task names such as `typecheck:go` |
| `docker-compose*.yml` | services, images, ports, env, init SQL |
| `vitest*.config.*`, `**/globalSetup*`, `.env.test*`, `.env.example` | test databases, fakes, required env vars |
| `prisma/schema.prisma` (any package) | codegen and migrate commands |
| `package.json` scripts | the repo's own format, lint, test, seed commands |

## 2. Draft, then edit

Run `devenv generate` for a first draft. It calls a hosted AI service, so if it
fails or the machine is offline, use `devenv init`. Treat either output as a
draft: rewrite it to the shape below and delete anything the repo does not
need. Keep the `.gitignore` entries `devenv init` adds (`.devenv*`,
`devenv.local.nix`, `.direnv`), or forge will refuse the dirty tree after the
first run. Commit `devenv.lock`.

## 3. devenv.nix shape

```nix
{ pkgs, config, ... }:
let
  port = process: name: toString config.processes.${process}.ports.${name}.value;
in
{
  languages.javascript = {
    enable = true;
    package = pkgs.nodejs_24;   # from .nvmrc
    pnpm.enable = true;         # check it matches packageManager; else leave pnpm ambient
  };

  # Both allocate their ports (processes.mysql.ports.main, processes.clickhouse-server.ports.*).
  services.mysql = {
    enable = true;
    initialDatabases = [ { name = "app_test"; } ];
  };
  services.clickhouse.enable = true;

  # Fakes are plain processes with a ready probe.
  processes.stripe-mock = {
    ports.http.allocate = 12111;
    exec = "stripe-mock -http-port ${port "stripe-mock" "http"}";
    ready.http.get = { port = config.processes.stripe-mock.ports.http.value; path = "/"; };
  };

  env = {
    FORGE_BASE = "main";        # optional; forge defaults to origin's HEAD branch
    DATABASE_URL = "mysql://root@127.0.0.1:${port "mysql" "main"}/app_test";
    CLICKHOUSE_URL = "http://127.0.0.1:${port "clickhouse-server" "http"}";
    STRIPE_API_BASE = "http://127.0.0.1:${port "stripe-mock" "http"}";
    STRIPE_SECRET_KEY = "sk_test_fake";   # fakes only; real secrets go through secretspec
  };

  tasks = {
    "forge:install" = { exec = "pnpm install --frozen-lockfile"; execIfModified = [ "pnpm-lock.yaml" ]; };
    "forge:codegen" = { exec = "pnpm -r exec prisma generate"; after = [ "forge:install" ];
                        execIfModified = [ "**/schema.prisma" ]; };
    "forge:migrate" = { exec = "pnpm db:migrate:test"; after = [ "forge:codegen" ];
                        execIfModified = [ "**/migrations/**" ]; };
    "forge:seed"    = { exec = "pnpm db:seed:test"; after = [ "forge:migrate" ];
                        execIfModified = [ "**/seed*" ]; };
    "forge:ready"   = { exec = "echo ready"; after = [ "forge:install" "forge:codegen" "forge:migrate" "forge:seed" ]; };

    # Gates. See "Gate contract" below.
    "forge:format".exec = ''
      grep -E '\.(c|m)?[jt]sx?$|\.json$' "$FORGE_CHANGED_FILES" | xargs -r pnpm exec oxfmt
    '';
    "forge:lint".exec = ''
      grep -E '\.(c|m)?[jt]sx?$' "$FORGE_CHANGED_FILES" | xargs -r pnpm exec oxlint --fix
      pnpm exec mop-lint --base "$FORGE_MERGE_BASE" --fix --json
    '';
    "forge:typecheck".exec = ''pnpm exec turbo run typecheck:go --filter="...[$FORGE_MERGE_BASE]"'';
    "forge:unit".exec = ''
      pnpm -r --filter "...[$FORGE_MERGE_BASE]" exec vitest run --changed "$FORGE_MERGE_BASE" --passWithNoTests
    '';
    "forge:integration".exec = ''
      files=$(grep -E '\.integration\.test\.[jt]sx?$' "$FORGE_CHANGED_FILES" || true)
      [ -n "$files" ] || { echo "no integration test files changed"; exit 0; }
      pnpm exec vitest run --config vitest.integration.config.ts $files
    '';
  };

  # One integration test file, so `devenv test` proves services, env and seed data.
  enterTest = "pnpm exec vitest run --config vitest.integration.config.ts path/to/one.integration.test.ts";
}
```

The commands are the Bask defaults. Replace each with what the repo actually
uses, verified against its scripts and configs. Rules that hold for every repo:

- **Toolchain.** Node from `.nvmrc`. Turn `pnpm.enable` on only if nixpkgs' pnpm
  matches `packageManager`, since a different major can ignore lockfile
  settings. Otherwise leave pnpm ambient (corepack).
- **Services.** Map compose services to `services.*` where devenv has one
  (`devenv search` or https://devenv.sh/services), else to a `processes.<name>`
  with `exec` and a `ready` probe (`ready.exec` or `ready.http.get`). Processes
  must not depend on `forge:*` tasks. forge starts them before `forge:ready`.
- **Ports per worktree.** Never hardcode a port two worktrees would share. Use
  `ports.<name>.allocate = <base>` and read `config.processes.<p>.ports.<name>.value`
  everywhere (env, probes, exec), so a second worktree gets the next free port.
- **Env.** Non-secret values in `env.*`. Real secrets are declared in
  `secretspec.toml` and enabled in devenv.yaml (`secretspec: { enable: true,
  provider: keyring }`), then read as `config.secretspec.secrets.NAME or ""`
  or loaded at runtime with `secretspec run -- <cmd>`. Never commit a value.
- **Setup tasks.** Chain them with `after` and give each `execIfModified`, so a
  rerun with unchanged inputs is a no-op. `forge:ready` runs after all of them.
  It is the one task forge calls for setup. The task cache does not know the
  database was wiped. After deleting `.devenv/state`, run
  `devenv tasks run --refresh-task-cache forge:ready`.

## Gate contract

forge runs each gate as `devenv tasks run --mode single --show-output forge:<gate>`
from the repo root, cheapest first, and stops at the first failure.

| Variable | Value |
| --- | --- |
| `FORGE_MERGE_BASE` | merge-base SHA of HEAD and the fetched base branch |
| `FORGE_BASE` | base branch name, e.g. `main` |
| `FORGE_CHANGED_FILES` | path to a file of repo-relative paths, one per line, added, copied, modified or renamed since the merge base (no deletions; may be empty) |

- **Exit code.** 0 passes, anything else blocks. A gate prints its findings to
  stdout or stderr. forge keeps the last 20 lines in its JSON and the full log on disk.
- **Format and lint fix in place.** forge commits their edits as
  `style: forge autofix`. `forge:lint` must exit nonzero only for findings it
  could not fix that block the merge. Warnings exit 0.
- **Scope to the diff.** Gates read `FORGE_CHANGED_FILES` or
  `FORGE_MERGE_BASE`, never the whole repo. Limits are 60 s for format and lint,
  300 s for each other gate, and 840 s for the whole run.
- **Every gate exists.** A repo with no integration tests still defines
  `forge:integration` (for example `echo "no integration tests"`). A missing
  task fails its gate.

## 4. Verify

1. `devenv up -d && devenv processes wait`. Every process should report ready.
2. `devenv tasks run forge:ready` twice. The second run executes no setup command.
3. `devenv test`. The single integration file passes.
4. Commit, then `forge push --check`. Every gate reports `passed`.
5. `devenv processes down`.

## Report

Reply with one JSON object:

```json
{
  "files": ["devenv.nix", "devenv.yaml", "devenv.lock", ".gitignore"],
  "services": ["mysql", "clickhouse", "stripe-mock"],
  "tasks": ["forge:install", "forge:codegen", "forge:migrate", "forge:seed", "forge:ready",
            "forge:format", "forge:lint", "forge:typecheck", "forge:unit", "forge:integration"],
  "healthy": true,
  "next": "commit the devenv files and run `forge push`"
}
```

`healthy` is true only when every step in Verify passed. Otherwise `next`
names the first step that failed and its error.
