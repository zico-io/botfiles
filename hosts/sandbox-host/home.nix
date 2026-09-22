# home-manager config for `percules`, the human login on sandbox-host.
#
# Machine-wide concerns stay in the system config; this file owns only what
# belongs to the session an agent or a person actually works in.
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
}
