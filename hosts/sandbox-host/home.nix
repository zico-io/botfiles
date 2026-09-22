# home-manager config for `percules`, the human login on sandbox-host.
#
# Machine-wide concerns stay in the system config; this file owns only what
# belongs to the session an agent or a person actually works in.
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
  #
  # claude-code and codex are the agents T3 Code launches over SSH. Installing
  # them declaratively costs them their self-update: both refuse to write into
  # the read-only store, so the version here is whatever the nixpkgs pin holds
  # until the flake is bumped. That is the trade this host wants - a deploy is
  # the only thing that changes what runs. `programs.nix-ld` (system config)
  # stays as the escape hatch for running a vendor installer by hand.
  #
  # With useUserPackages these land in /etc/profiles/per-user/percules/bin,
  # which is the absolute path to give T3 Code if a non-login SSH shell hands
  # it a thin PATH.
  home.packages = with pkgs; [
    claude-code
    codex
    fd
    gh
  ];
}
