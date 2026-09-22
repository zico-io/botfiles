# home-manager config for `percules`, the human login on sandbox-host.
#
# Machine-wide concerns stay in the system config; this file owns only what
# belongs to the session an agent or a person actually works in.
#
# The agent CLIs themselves (claude, codex) are deliberately absent: they ship
# as self-updating vendor binaries on a weekly cadence, so pinning them to a
# nixpkgs revision would hold them back and add an unfree flag to the whole
# host. `programs.nix-ld` is what makes their own installers work here.
{ pkgs, ... }:
{
  home.stateVersion = "26.05";

  # Commits made from an agent session on this host would otherwise be authored
  # by `percules@sandbox-host`.
  programs.git = {
    enable = true;
    settings.user = {
      name = "Nico Zamora";
      email = "dev@zico.xyz";
    };
  };

  programs.helix = {
    enable = true;
    defaultEditor = true;
    # This repo is mostly Nix, and an agent that can ask an LSP beats an agent
    # that greps.
    extraPackages = [
      pkgs.nil
      pkgs.nixfmt
    ];
  };

  # Every repo here is a flake, so `cd` into one should be enough to get its
  # toolchain. nix-direnv keeps the dev shell in the store instead of
  # re-evaluating it on each entry.
  programs.direnv = {
    enable = true;
    nix-direnv.enable = true;
  };

  # git, jq, ripgrep, and tmux are system-wide already; these are the gaps an
  # agent session hits.
  home.packages = with pkgs; [
    fd
    gh
  ];
}
