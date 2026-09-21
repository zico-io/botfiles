# services.microsandbox - the microVM runtime layer of the sandbox host.
#
# Scope note: microsandbox 0.7.x is a CLI, not a daemon. There is no upstream
# server/API to supervise, so this module provisions the runtime (state, KVM
# access, resource ceilings, warm images) and leaves remote access to the
# tailnet module. An HTTP job API on top of `msb` would be a service we write.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.services.microsandbox;
in
{
  options.services.microsandbox = {
    enable = lib.mkEnableOption "the microsandbox microVM runtime";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../pkgs/microsandbox.nix { };
      defaultText = lib.literalExpression "pkgs.callPackage ../pkgs/microsandbox.nix { }";
      description = "The msb build to install and run.";
    };

    stateDir = lib.mkOption {
      type = lib.types.path;
      default = "/var/lib/microsandbox";
      description = ''
        MSB_HOME: images, sandboxes, and overlays live here. Point it at the
        NVMe-backed workspace disk, never at the root disk.
      '';
    };

    group = lib.mkOption {
      type = lib.types.str;
      default = "microsandbox";
      description = ''
        Group owning the state directory. Add every human who should be able to
        drive `msb` interactively to it.
      '';
    };

    images = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      example = [ "docker.io/library/debian:trixie-slim" ];
      description = "Images pulled at boot so the first job does not pay for the fetch.";
    };

    cpuQuota = lib.mkOption {
      type = lib.types.str;
      default = "600%";
      description = ''
        Total CPU across every sandbox, as a systemd CPUQuota. The default
        leaves 2 of the host's 8 vCPU for the OS, so agent jobs cannot make the
        box unreachable.
      '';
    };

    memoryMax = lib.mkOption {
      type = lib.types.str;
      default = "36G";
      description = ''
        Total memory across every sandbox. Keep this well under the VM's RAM:
        the remainder is the OS, page cache, and burst headroom.
      '';
    };

    tasksMax = lib.mkOption {
      type = lib.types.int;
      default = 8192;
      description = "Total process/thread ceiling across every sandbox.";
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ cfg.package ];
    environment.sessionVariables.MSB_HOME = toString cfg.stateDir;

    users.groups.${cfg.group} = { };

    systemd.tmpfiles.rules = [
      "d ${cfg.stateDir} 2770 root ${cfg.group} -"
    ];

    # Bounds the units this module manages. Sandboxes an operator or agent
    # starts from an interactive session land in their own user slice instead,
    # so this is a floor on host protection, not a total cap. Documented rather
    # than papered over; tighten with a per-user slice if agents get their own
    # login accounts.
    systemd.slices.microsandbox = {
      description = "microsandbox microVM workloads";
      sliceConfig = {
        CPUAccounting = true;
        MemoryAccounting = true;
        TasksAccounting = true;
        CPUQuota = cfg.cpuQuota;
        MemoryMax = cfg.memoryMax;
        TasksMax = cfg.tasksMax;
      };
    };

    # `msb doctor` exits non-zero without CPU virtualization or /dev/kvm, so a
    # hypervisor with nested virtualization switched off fails here at boot
    # rather than at the first agent job.
    systemd.services.microsandbox-preflight = {
      description = "Verify host virtualization prerequisites for microsandbox";
      wantedBy = [ "multi-user.target" ];
      after = [ "local-fs.target" ];
      environment.MSB_HOME = toString cfg.stateDir;
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = "${lib.getExe cfg.package} doctor";
        ProtectHome = true;
        ProtectSystem = "strict";
        ReadWritePaths = [ cfg.stateDir ];
        NoNewPrivileges = true;
      };
    };

    systemd.services.microsandbox-images = lib.mkIf (cfg.images != [ ]) {
      description = "Pre-pull microsandbox base images";
      wantedBy = [ "multi-user.target" ];
      wants = [ "network-online.target" ];
      requires = [ "microsandbox-preflight.service" ];
      after = [
        "microsandbox-preflight.service"
        "network-online.target"
      ];
      environment.MSB_HOME = toString cfg.stateDir;
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        Slice = "microsandbox.slice";
        ExecStart = map (image: "${lib.getExe cfg.package} pull ${lib.escapeShellArg image}") cfg.images;
        ProtectHome = true;
        ProtectSystem = "strict";
        ReadWritePaths = [ cfg.stateDir ];
        NoNewPrivileges = true;
      };
    };
  };
}
