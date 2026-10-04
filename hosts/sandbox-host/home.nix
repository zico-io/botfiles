# home-manager config shared by the human logins on sandbox-host.
#
# Machine-wide concerns stay in the system config; this file owns only what
# belongs to the session an agent or a person actually works in.
{ pkgs, ... }:
{
  home.stateVersion = "26.05";

  home.file.".claude/AGENTS.md".source = "${pkgs.botfiles}/share/botfiles/AGENTS.md";
  home.file.".codex/AGENTS.md".source = "${pkgs.botfiles}/share/botfiles/AGENTS.md";

  # The identity itself is per user, set next to each login in default.nix.
  programs.git.enable = true;

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
  # claude-code and codex are the agents T3 Code launches over SSH. They come
  # from llm-agents.nix, which tracks upstream releases daily, rather than
  # nixpkgs, which lags them by weeks. Installing them declaratively still
  # costs them their self-update: both refuse to write into the read-only
  # store, so the version here is whatever the llm-agents pin holds until
  # `nix flake update llm-agents`. That is the trade this host wants - a deploy is
  # the only thing that changes what runs. `programs.nix-ld` (system config)
  # stays as the escape hatch for running a vendor installer by hand.
  #
  # With useUserPackages these land in /etc/profiles/per-user/<user>/bin,
  # which is the absolute path to give T3 Code if a non-login SSH shell hands
  # it a thin PATH.
  home.packages = with pkgs; [
    llm-agents.claude-code
    llm-agents.codex
    t3code
    botfiles
    fd
    gh
  ];
}
