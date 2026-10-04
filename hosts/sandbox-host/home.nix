# home-manager config shared by the human logins on sandbox-host.
#
# Machine-wide concerns stay in the system config; this file owns only what
# belongs to the session an agent or a person actually works in.
{ lib, pkgs, ... }:
{
  home.stateVersion = "26.05";

  home.file.".claude/AGENTS.md".source = "${pkgs.botfiles}/share/botfiles/AGENTS.md";
  home.file.".codex/AGENTS.md".source = "${pkgs.botfiles}/share/botfiles/AGENTS.md";

  # Bask-Health/skills is authored once and read live: this clone is the toolbox's
  # default skill root, fast-forwarded every 15 minutes. Uses the login's
  # `gh auth`; until that exists the unit fails and the toolbox skips the root.
  systemd.user.services.bask-skills = {
    Unit.Description = "Pull Bask-Health/skills";
    Service = {
      Type = "oneshot";
      ExecStart = pkgs.writeShellScript "bask-skills-pull" ''
        dir="$HOME/.local/share/bask-skills"
        if [ -d "$dir/.git" ]; then
          ${lib.getExe pkgs.git} -C "$dir" -c credential.helper='!${lib.getExe pkgs.gh} auth git-credential' pull --ff-only -q
        else
          ${lib.getExe pkgs.gh} repo clone Bask-Health/skills "$dir" -- -q
        fi
      '';
      Environment = [ "PATH=${lib.makeBinPath [ pkgs.git ]}" ];
    };
  };
  systemd.user.timers.bask-skills = {
    Timer = {
      OnStartupSec = "1min";
      OnUnitActiveSec = "15min";
    };
    Install.WantedBy = [ "timers.target" ];
  };

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
