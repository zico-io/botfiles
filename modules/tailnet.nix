# services.tailnetNode - the host's only durable network identity.
#
# Deny by default: nothing is reachable from the LAN, everything is reachable
# from the tailnet. Recovery when tailscale itself is down is the hypervisor's
# VNC console, which is why no LAN SSH hole is punched here.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.services.tailnetNode;
  tailscale = config.services.tailscale.package;

  # One tailscaled per extra tailnet, each with its own state, socket, and
  # WireGuard port. They run with userspace networking: two kernel-mode
  # daemons would fight over routing table 52, the fwmark, and resolved's DNS.
  # Netstack still terminates Tailscale SSH in-process and forwards other
  # inbound TCP to localhost, so the node is fully reachable from that tailnet.
  # ponytail: no transparent outbound into extra tailnets, dial through
  # `tailscale-<name> nc` or run the daemon with --socks5-server if that
  # is ever needed.
  extraSocket = name: "/run/tailscale-${name}/tailscaled.sock";
  extraCli =
    name:
    pkgs.writeShellScriptBin "tailscale-${name}" ''
      exec ${tailscale}/bin/tailscale --socket=${extraSocket name} "$@"
    '';
  upFlags =
    {
      hostname,
      tags,
      ssh,
    }:
    [ "--hostname=${hostname}" ]
    ++ lib.optional ssh "--ssh"
    ++ lib.optional (tags != [ ]) "--advertise-tags=${lib.concatStringsSep "," tags}";
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

    extraTailnets = lib.mkOption {
      default = { };
      example = lib.literalExpression ''
        { bask = { port = 41642; tags = [ "tag:sandbox-host" ]; }; }
      '';
      description = ''
        Further tailnets to join alongside the primary one, keyed by a short
        name. Each gets its own tailscaled and a `tailscale-<name>` CLI. With
        no auth key, join once by hand: `sudo tailscale-<name> up` with the
        same flags this module passes, then log in as a tag owner.
      '';
      type = lib.types.attrsOf (
        lib.types.submodule {
          options = {
            port = lib.mkOption {
              type = lib.types.port;
              description = "WireGuard UDP port; must differ from every other tailscaled.";
            };
            hostname = lib.mkOption {
              type = lib.types.str;
              default = cfg.hostname;
              defaultText = lib.literalExpression "config.services.tailnetNode.hostname";
            };
            tags = lib.mkOption {
              type = lib.types.listOf lib.types.str;
              default = cfg.tags;
              defaultText = lib.literalExpression "config.services.tailnetNode.tags";
            };
            ssh = lib.mkOption {
              type = lib.types.bool;
              default = cfg.ssh;
              defaultText = lib.literalExpression "config.services.tailnetNode.ssh";
            };
            authKeyFile = lib.mkOption {
              type = lib.types.nullOr lib.types.str;
              default = null;
            };
          };
        }
      );
    };
  };

  config = lib.mkIf cfg.enable {
    # Tailscale hands DNS to resolved instead of rewriting /etc/resolv.conf.
    # Direct mode leaves MagicDNS as the only nameserver, and when tailscaled
    # wins the boot race against DHCP it captures no upstream at all: tailnet
    # names resolve, every public name fails. resolved keeps the DHCP
    # nameservers and routes only ts.net to MagicDNS.
    services.resolved.enable = true;

    services.tailscale = {
      enable = true;
      useRoutingFeatures = "none";
      authKeyFile = cfg.authKeyFile;
      extraUpFlags = upFlags { inherit (cfg) hostname tags ssh; };
    };

    environment.systemPackages = lib.mapAttrsToList (name: _: extraCli name) cfg.extraTailnets;

    systemd.services = lib.concatMapAttrs (
      name: t:
      {
        "tailscaled-${name}" = {
          description = "Tailscale node agent for the ${name} tailnet";
          wantedBy = [ "multi-user.target" ];
          wants = [ "network-online.target" ];
          after = [ "network-online.target" ];
          # tailscaled shells out to getent/su for Tailscale SSH sessions.
          path = [
            pkgs.getent
            pkgs.shadow
          ];
          serviceConfig = {
            ExecStart = lib.concatStringsSep " " [
              "${tailscale}/bin/tailscaled"
              "--tun=userspace-networking"
              "--statedir=/var/lib/tailscale-${name}"
              "--socket=${extraSocket name}"
              "--port=${toString t.port}"
            ];
            StateDirectory = "tailscale-${name}";
            StateDirectoryMode = "0700";
            RuntimeDirectory = "tailscale-${name}";
            Restart = "on-failure";
          };
        };
      }
      // lib.optionalAttrs (t.authKeyFile != null) {
        "tailscaled-${name}-autoconnect" = {
          description = "Join the ${name} tailnet with an auth key";
          wantedBy = [ "multi-user.target" ];
          after = [ "tailscaled-${name}.service" ];
          requires = [ "tailscaled-${name}.service" ];
          serviceConfig.Type = "oneshot";
          # Only on first join: once logged in, the flags live in tailscaled's
          # state and a reused key must not re-register the node.
          script = ''
            cli=${extraCli name}/bin/tailscale-${name}
            until state=$($cli status --json --peers=false | ${lib.getExe pkgs.jq} -r .BackendState) && [ -n "$state" ] && [ "$state" != NoState ]; do
              sleep 0.5
            done
            if [ "$state" = NeedsLogin ]; then
              $cli up --auth-key="file:${t.authKeyFile}" --accept-dns=false ${
                lib.escapeShellArgs (upFlags {
                  inherit (t) hostname tags ssh;
                })
              }
            fi
          '';
        };
      }
    ) cfg.extraTailnets;

    networking.firewall = {
      enable = true;
      allowedTCPPorts = [ ];
      allowedUDPPorts = [
        config.services.tailscale.port
      ]
      ++ lib.mapAttrsToList (_: t: t.port) cfg.extraTailnets;
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
