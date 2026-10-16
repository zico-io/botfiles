# services.bench-hub - Home Manager user services for Bench's hub (apps/hub in
# zico-io/bench): the server that holds every bench-device machine's tunnel and
# every app client's stream.
#
# zico-io/bench is private, so it is not a flake input: CI would need a token
# to evaluate this host. Like bask-skills, a timer keeps a clone fresh with the
# login's `gh auth`, installs only the hub's dependencies, and restarts the hub
# when main moves. The hub runs from source with tsx, as bench ships it.
#
# Secrets stay outside the store: the hub reads its database URL and auth
# secret from envFile (mode 0600), which `infra/backend/hub-secrets.sh` in
# bench writes. Until that file and apps/hub/bin/hub.js exist,
# the hub does not start.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.services.bench-hub;
  node = lib.getExe cfg.nodejs;
in
{
  options.services.bench-hub = {
    enable = lib.mkEnableOption "Bench's hub";

    nodejs = lib.mkPackageOption pkgs "nodejs_24" { };

    dir = lib.mkOption {
      type = lib.types.str;
      default = "${config.xdg.dataHome}/bench-hub";
      defaultText = lib.literalExpression ''"''${config.xdg.dataHome}/bench-hub"'';
      description = "The zico-io/bench clone the hub runs from.";
    };

    ref = lib.mkOption {
      type = lib.types.str;
      default = "main";
      description = "Branch the clone follows.";
    };

    envFile = lib.mkOption {
      type = lib.types.str;
      default = "${config.xdg.configHome}/bench-hub/env";
      defaultText = lib.literalExpression ''"''${config.xdg.configHome}/bench-hub/env"'';
      description = "DATABASE_URL, BETTER_AUTH_SECRET, BETTER_AUTH_URL, CORS_ORIGINS and optionally AI_GATEWAY_API_KEY.";
    };

    port = lib.mkOption {
      type = lib.types.port;
      default = 18687;
      description = "Port the hub listens on. It binds every interface; the firewall admits only tailscale0.";
    };
  };

  config = lib.mkIf cfg.enable {
    systemd.user.services.bench-hub-update = {
      Unit.Description = "Pull zico-io/bench and install the hub's dependencies";
      Service = {
        Type = "oneshot";
        ExecStart = pkgs.writeShellScript "bench-hub-update" ''
          set -euo pipefail
          dir=${lib.escapeShellArg cfg.dir}
          git=(${lib.getExe pkgs.git} -c credential.helper='!${lib.getExe pkgs.gh} auth git-credential')
          if [ -d "$dir/.git" ]; then
            before=$(git -C "$dir" rev-parse HEAD)
            "''${git[@]}" -C "$dir" fetch -q origin ${lib.escapeShellArg cfg.ref}
            git -C "$dir" checkout -q --detach FETCH_HEAD
          else
            before=none
            # HTTPS through gh's credential helper, not `gh repo clone`, which follows
            # the login's git_protocol and may want ssh.
            "''${git[@]}" clone -q --branch ${lib.escapeShellArg cfg.ref} https://github.com/zico-io/bench.git "$dir"
          fi
          after=$(git -C "$dir" rev-parse HEAD)
          if [ "$before" != "$after" ] || [ ! -d "$dir/apps/hub/node_modules" ]; then
            # --ignore-scripts: the root's lefthook install has no business on a server.
            (cd "$dir" && corepack pnpm install --frozen-lockfile --prod --ignore-scripts --filter "@repo/hub...")
            # restart, not try-restart: it also starts a hub its conditions held back.
            systemctl --user restart bench-hub.service
          fi
        '';
        Environment = [
          "PATH=${
            lib.makeBinPath [
              pkgs.git
              cfg.nodejs
              pkgs.systemd
            ]
          }"
          "COREPACK_ENABLE_DOWNLOAD_PROMPT=0"
        ];
      };
    };

    systemd.user.timers.bench-hub-update = {
      Timer = {
        OnStartupSec = "1min";
        OnUnitActiveSec = "15min";
      };
      Install.WantedBy = [ "timers.target" ];
    };

    systemd.user.services.bench-hub = {
      Unit = {
        Description = "Bench hub";
        ConditionPathExists = [
          cfg.envFile
          "${cfg.dir}/apps/hub/bin/hub.js"
        ];
      };
      Service = {
        ExecStart = "${node} apps/hub/bin/hub.js";
        WorkingDirectory = cfg.dir;
        EnvironmentFile = cfg.envFile;
        Environment = [
          "PORT=${toString cfg.port}"
          "NODE_ENV=production"
          "NODE_NO_WARNINGS=1"
        ];
        Restart = "always";
        RestartSec = 2;
      };
      Install.WantedBy = [ "default.target" ];
    };
  };
}
