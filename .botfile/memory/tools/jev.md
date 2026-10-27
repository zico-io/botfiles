# jev - TypeSafe Jev typed judgments from the shell

- `pkgs/jev-cli.nix` packages the PyPI sdist of `jev-cli` (github tumf/jev-cli, unofficial, MIT) for sandbox-host; agents call `jev noul|choice|score|run` for cheap probability, choice, or score answers instead of generated prose <source: user request + PyPI jev-cli 0.7.0, 2026-10-12>
- Only the `jev` CLI ships: upstream `jev-mcp` needs `mcp>=2.2` (deps `httpx2`, `mcp-types`) and nixpkgs 26.05 has `mcp` 1.26; the CLI is stdlib-only. Revisit once nixpkgs carries mcp 2.x <source: pyproject.toml + nixpkgs eval, 2026-10-12>
- Upstream pins `uv_build<0.9`; the package relaxes it for nixpkgs' 0.10 and builds cleanly <source: nix build, 2026-10-12>
- Key precedence: an exported `TYPESAFE_API_KEY` wins, then the sops secret `typesafe-api-key` (`/run/secrets/typesafe-api-key`, group `users`, 0440) read by the per-login wrapper, then `~/.config/jev-cli/credentials.json` from `jev auth set` <source: jev_cli api_key() + wrapper test, 2026-10-12>
- The bundled skill is linked to `~/.claude/toolbox-skills/jev-cli`, so the toolbox finds it; it still mentions `jev-mcp`, which is absent here <source: hosts/sandbox-host/home.nix, 2026-10-12>
- No host installs jev any more: sandbox-host became a k3s pool node with no logins, and `typesafe-api-key` left its sops file. The package stays exported for other hosts <source: hosts/sandbox-host/default.nix, 2026-10-27>
