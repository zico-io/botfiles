# rescue - a NixOS live ISO for reaching a guest whose own access is broken.
#
# Boot it as a VM's CD-ROM (TrueNAS: `midclt call vm.device.create` with dtype
# CDROM, then restart the VM). It takes a LAN address by DHCP and admits root
# over SSH with the keys below only, so the guest's disks can be mounted,
# repaired, or reinstalled with `nixos-install --flake`. Detach it afterwards:
# while it is attached, every boot lands here instead of the guest.
{
  lib,
  modulesPath,
  pkgs,
  ...
}:

{
  imports = [ "${modulesPath}/installer/cd-dvd/installation-cd-minimal.nix" ];

  image.baseName = lib.mkForce "botfiles-rescue";
  networking.hostName = "rescue";

  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "prohibit-password";
    };
  };
  users.users.root.openssh.authorizedKeys.keys = import ./keys.nix;

  nix.settings.experimental-features = [
    "nix-command"
    "flakes"
  ];

  environment.systemPackages = with pkgs; [
    age
    git
    rsync
    sops
    ssh-to-age
    tailscale
  ];
}
