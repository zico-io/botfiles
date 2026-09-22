# sandbox-host - NixOS guest on the bare-metal TrueNAS box (Ryzen 9 5900X,
# 128 GB). Runs microsandbox microVMs for coding agents, reachable only over
# the tailnet.
#
# The NAS is a storage appliance, not the execution boundary: agents run
# arbitrary repository code, so they get a guest kernel of their own and no
# path back to ZFS datasets, the TrueNAS UI, or the LAN.
#
# Hypervisor settings this config assumes (TrueNAS -> Virtual Machines):
#   8 cores / 1 vCPU / 1 thread, host CPU passthrough, nested virtualization ON
#   48 GiB fixed memory (leave "minimum memory" empty; ballooning and microVMs
#   are a bad pairing), UEFI boot, VirtIO disks and NIC on the LAN bridge.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  # sops-nix is wired only once the operator has created the encrypted file
  # (see secrets/README.md), so a fresh checkout still evaluates.
  secretsFile = ../../secrets/sandbox-host.yaml;
  haveSecrets = builtins.pathExists secretsFile;
in
{
  imports = [ ./disko.nix ];

  networking.hostName = "sandbox-host";
  networking.useDHCP = lib.mkDefault true;
  time.timeZone = "UTC";

  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;

  boot.initrd.availableKernelModules = [
    "virtio_pci"
    "virtio_blk"
    "virtio_scsi"
    "virtio_net"
    "sd_mod"
  ];

  # kvm-amd is the whole point of this host: microsandbox boots real microVMs,
  # so the guest needs nested virtualization from the hypervisor.
  boot.kernelModules = [ "kvm-amd" ];
  boot.kernelParams = [
    "amd_iommu=on"
    "iommu=pt"
  ];
  hardware.cpu.amd.updateMicrocode = true;

  # Build, test, and language-server workloads run many watchers and mappings
  # at once; the stock limits are the first thing a monorepo job hits.
  boot.kernel.sysctl = {
    "fs.inotify.max_user_watches" = 1048576;
    "fs.inotify.max_user_instances" = 4096;
    "fs.file-max" = 2097152;
    "vm.max_map_count" = 1048576;
    "kernel.pid_max" = 4194304;
  };

  services.qemuGuest.enable = true;

  services.tailnetNode = {
    enable = true;
    hostname = "sandbox-host";
    tags = [ "tag:sandbox-host" ];
    authKeyFile = lib.mkIf haveSecrets config.sops.secrets.tailscale-authkey.path;
  };

  services.microsandbox = {
    enable = true;
    stateDir = "/var/lib/microsandbox";
    # 6 of 8 vCPU and 36 of 48 GiB: the remainder is the OS, page cache, and
    # the burst headroom that keeps the box answerable while jobs are running.
    cpuQuota = "600%";
    memoryMax = "36G";
  };

  sops = lib.mkIf haveSecrets {
    defaultSopsFile = secretsFile;
    age.sshKeyPaths = [ "/etc/ssh/ssh_host_ed25519_key" ];
    secrets.tailscale-authkey = { };
  };

  users.users.admin = {
    isNormalUser = true;
    extraGroups = [
      "wheel"
      "kvm" # /dev/kvm, without which msb cannot boot a sandbox
      config.services.microsandbox.group
    ];
    openssh.authorizedKeys.keys = import ./admin-keys.nix;
  };

  # This host has no password anywhere: no password SSH, no password console
  # login, and tailnet identity is the authentication boundary. Prompting for a
  # password that was never set would only make sudo unusable.
  security.sudo.wheelNeedsPassword = false;

  # T3 Code's remote runtime, and the agent CLIs it launches, are prebuilt
  # glibc executables: NixOS has no /lib64/ld-linux, so they fail with a
  # misleading "no such file or directory" without a loader shim.
  programs.nix-ld.enable = true;

  environment.systemPackages = with pkgs; [
    btop
    git
    jq
    ripgrep
    tmux
    vim
  ];

  nix = {
    settings = {
      experimental-features = [
        "nix-command"
        "flakes"
      ];
      auto-optimise-store = true;
      trusted-users = [
        "root"
        "admin"
      ];
      max-jobs = 8;
      cores = 8;
    };
    gc = {
      automatic = true;
      dates = "weekly";
      options = "--delete-older-than 14d";
    };
  };

  # Pinned to the release this host was installed from. Changing it on an
  # upgrade migrates stateful services underneath you; leave it alone.
  system.stateVersion = "26.05";
}
