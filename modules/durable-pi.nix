# services.durable-pi - Home Manager user services for Durable Pi: the device
# backend (agents) on loopback and the playground hub (web UI) for the tailnet.
#
# The hub has no login and holds every device token, so serving it beyond
# loopback requires tailnetAllow: the hub asks tailscaled who is behind each
# connection's source address and admits only those logins on untagged nodes.
#
# Secrets stay outside the store: the backend reads its token and model key
# from <home>/backend.env, which `just net up local` writes (mode 0600).
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.services.durable-pi;
  root = "${cfg.package}/${cfg.package.root}";
  node = lib.getExe cfg.package.nodejs;
  tsx = app: "${root}/${app}/node_modules/tsx/dist/cli.mjs";
  loopback = lib.elem cfg.hub.host [
    "127.0.0.1"
    "localhost"
    "::1"
  ];
in
{
  options.services.durable-pi = {
    enable = lib.mkEnableOption "the Durable Pi backend and hub";

    package = lib.mkPackageOption pkgs "durable-pi" { };

    home = lib.mkOption {
      type = lib.types.str;
      default = "${config.home.homeDirectory}/.dpi";
      defaultText = lib.literalExpression ''"''${config.home.homeDirectory}/.dpi"'';
      description = "DPI_HOME: backend.env, backend data and the hub's network.sqlite.";
    };

    backend = {
      enable = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "Run this machine's dpi-backend. It starts only once <home>/backend.env exists.";
      };
      path = lib.mkOption {
        type = lib.types.str;
        default = "${config.home.profileDirectory}/bin:/run/wrappers/bin:/run/current-system/sw/bin";
        defaultText = lib.literalExpression ''"''${config.home.profileDirectory}/bin:/run/wrappers/bin:/run/current-system/sw/bin"'';
        description = "PATH for the agents' shell tools: the login's own packages, not the unit's bare default.";
      };
    };

    hub = {
      enable = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "Run the playground hub and web UI.";
      };
      host = lib.mkOption {
        type = lib.types.str;
        default = "127.0.0.1";
        example = "0.0.0.0";
        description = "Bind address. Anything other than loopback requires tailnetAllow.";
      };
      port = lib.mkOption {
        type = lib.types.port;
        default = 4781;
      };
      tailnetAllow = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [ ];
        example = [ "you@example.com" ];
        description = "Tailscale logins admitted to the hub. Empty turns the identity gate off.";
      };
      networkFile = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "/home/you/durable-pi/dpi-network.yaml";
        description = "dpi-network.yaml to seed devices from. Null uses only the registry `just net` wrote.";
      };
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = !cfg.hub.enable || loopback || cfg.hub.tailnetAllow != [ ];
        message = "services.durable-pi.hub.host is ${cfg.hub.host}: set hub.tailnetAllow so the hub requires a tailnet identity.";
      }
    ];

    systemd.user.services.dpi-backend = lib.mkIf cfg.backend.enable {
      Unit = {
        Description = "Durable Pi device server (dpi-backend)";
        ConditionPathExists = "${cfg.home}/backend.env";
      };
      Service = {
        ExecStart = "${node} ${tsx "dpi-backend"} src/main.ts";
        WorkingDirectory = "${root}/dpi-backend";
        Environment = [
          "DPI_HOME=${cfg.home}"
          "NODE_NO_WARNINGS=1"
          "PATH=${cfg.backend.path}"
        ];
        Restart = "always";
        RestartSec = 2;
        TimeoutStopSec = 20;
      };
      Install.WantedBy = [ "default.target" ];
    };

    systemd.user.services.dpi-hub = lib.mkIf cfg.hub.enable {
      Unit = {
        Description = "Durable Pi hub and web UI";
        After = lib.optional cfg.backend.enable "dpi-backend.service";
      };
      Service = {
        ExecStart = "${node} ${tsx "dpi-playground"} server.ts --host ${cfg.hub.host} --port ${toString cfg.hub.port}";
        WorkingDirectory = "${root}/dpi-playground";
        Environment = [
          "DPI_HOME=${cfg.home}"
          "NODE_NO_WARNINGS=1"
        ]
        ++ lib.optional (
          cfg.hub.tailnetAllow != [ ]
        ) "DPI_HUB_TAILNET_ALLOW=${lib.concatStringsSep "," cfg.hub.tailnetAllow}"
        ++ lib.optional (cfg.hub.networkFile != null) "DPI_NETWORK_FILE=${cfg.hub.networkFile}";
        # tailscaled may not be up yet at boot; the hub exits and retries.
        Restart = "always";
        RestartSec = 5;
      };
      Install.WantedBy = [ "default.target" ];
    };
  };
}
