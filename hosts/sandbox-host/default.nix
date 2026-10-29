# sandbox-host - NixOS guest on the bare-metal TrueNAS box (Ryzen 9 5900X,
# 128 GB). A pool node of the yggdrasil k3s cluster (k3s.nix): it runs coding
# agent sandboxes as Kata VMs and hosts no logins of its own.
#
# The NAS is a storage appliance, not the execution boundary: agents run
# arbitrary repository code, so they get a guest kernel of their own and no
# path back to ZFS datasets, the TrueNAS UI, or the LAN.
#
# Hypervisor settings this config assumes (TrueNAS -> Virtual Machines):
#   8 cores / 1 vCPU / 1 thread, host CPU passthrough, nested virtualization ON
#   48 GiB fixed memory (leave "minimum memory" empty; ballooning and nested
#   VMs are a bad pairing), UEFI boot, VirtIO disks and NIC on the LAN bridge.
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
  imports = [
    ./disko.nix
    ./k3s.nix
  ];

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

  # kvm-amd is the whole point of this host: every sandbox is a Kata VM,
  # so the guest needs nested virtualization from the hypervisor.
  boot.kernelModules = [ "kvm-amd" ];
  boot.kernelParams = [
    "amd_iommu=on"
    "iommu=pt"
  ];
  # The qxl DRM driver for TrueNAS's SPICE display wedges under load ("[TTM]
  # Buffer eviction failed" every 15 s), which froze the console and hung a
  # shutdown for 15 minutes. Without it the console runs on the UEFI
  # framebuffer through simpledrm, which SPICE shows the same.
  boot.blacklistedKernelModules = [ "qxl" ];
  hardware.cpu.amd.updateMicrocode = true;

  services.qemuGuest.enable = true;

  # Break-glass only. Pool nodes are interchangeable and never user-facing;
  # users reach `sandbox`, the gateway, not a host.
  services.tailnetNode = {
    enable = true;
    hostname = "sandbox-pool-1";
    tags = [ "tag:sandbox-pool" ];
    authKeyFile = lib.mkIf haveSecrets config.sops.secrets.tailscale-authkey.path;
  };

  # A bootstrap token (`k3s token create`) only joins agents, so this host
  # never holds a credential that could join a server.
  services.k3s.tokenFile = lib.mkIf haveSecrets config.sops.secrets.k3s-token.path;

  sops = lib.mkIf haveSecrets {
    defaultSopsFile = secretsFile;
    age.sshKeyPaths = [ "/etc/ssh/ssh_host_ed25519_key" ];
    secrets.tailscale-authkey = { };
    secrets.k3s-token = { };
  };

  users.users.admin = {
    isNormalUser = true;
    extraGroups = [ "wheel" ];
    openssh.authorizedKeys.keys = import ./admin-keys.nix;
  };

  # This host has no password anywhere: no password SSH, no password console
  # login, and tailnet identity is the authentication boundary. Prompting for a
  # password that was never set would only make sudo unusable.
  security.sudo.wheelNeedsPassword = false;

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
