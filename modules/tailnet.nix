# services.tailnetNode - the host's only durable network identity.
#
# Deny by default: nothing is reachable from the LAN, everything is reachable
# from the tailnet. Recovery when tailscale itself is down is the hypervisor's
# VNC console, which is why no LAN SSH hole is punched here.
{
  config,
  lib,
  ...
}:

let
  cfg = config.services.tailnetNode;
in
{
  options.services.tailnetNode = {
    enable = lib.mkEnableOption "the tailnet-only access posture";

    hostname = lib.mkOption {
      type = lib.types.str;
      default = config.networking.hostName;
      defaultText = lib.literalExpression "config.networking.hostName";
      description = "MagicDNS name to claim on the tailnet.";
    };

    tags = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      example = [ "tag:sandbox-host" ];
      description = ''
        Tailscale ACL tags advertised at login. Tags give the machine a
        purpose-based identity, so policy never hangs off an operator's
        personal account. Requires a tag-owning auth key.
      '';
    };

    ssh = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = ''
        Advertise Tailscale SSH. This is the primary access path: it makes
        tailnet policy, not a committed public key, the authentication
        boundary. A session still needs both a network rule and an SSH rule.
      '';
    };

    authKeyFile = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = ''
        Path to a file holding a tag-owning auth key, for unattended first
        join. Null means the host is joined once by hand from the console.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    services.tailscale = {
      enable = true;
      useRoutingFeatures = "none";
      authKeyFile = cfg.authKeyFile;
      extraUpFlags =
        [ "--hostname=${cfg.hostname}" ]
        ++ lib.optional cfg.ssh "--ssh"
        ++ lib.optional (cfg.tags != [ ]) "--advertise-tags=${lib.concatStringsSep "," cfg.tags}";
    };

    networking.firewall = {
      enable = true;
      allowedTCPPorts = [ ];
      allowedUDPPorts = [ config.services.tailscale.port ];
      trustedInterfaces = [ "tailscale0" ];
    };

    services.openssh = {
      enable = true;
      # Reachable over tailscale0 only, via trustedInterfaces above.
      openFirewall = false;
      settings = {
        PasswordAuthentication = false;
        KbdInteractiveAuthentication = false;
        PermitRootLogin = "no";
      };
    };
  };
}
