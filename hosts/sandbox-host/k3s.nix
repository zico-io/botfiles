# sandbox-host as a pool node of the yggdrasil k3s cluster (gitlab percs/yggdrasil).
#
# The node contributes vCPU to the sandbox pool and nothing else: the taint
# keeps every workload off it except pods that tolerate `pool=sandbox`, and the
# `kata` runtime gives each of those pods its own guest kernel. Users never
# address this host; they reach `sandbox` through the gateway.
{

  lib,
  pkgs,
  ...
}:

let
  # yggdrasil's three servers. kubelet and flannel accept only these.
  servers = [
    "192.168.12.20"
    "192.168.12.21"
    "192.168.12.22"
  ];
  kataConfig = "${pkgs.kata-runtime}/share/defaults/kata-containers/configuration-qemu.toml";
in
{
  services.k3s = {
    enable = true;
    role = "agent";
    # Same minor as the servers and never newer: an agent ahead of its control
    # plane is outside the Kubernetes skew policy.
    package = pkgs.k3s_1_36;
    serverAddr = "https://192.168.12.30:6443";
    nodeIP = "192.168.12.243";
    nodeLabel = [ "pool=sandbox" ];
    nodeTaint = [ "pool=sandbox:NoSchedule" ];
    containerdConfigTemplate = ''
      {{ template "base" . }}

      [plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.kata]
        runtime_type = "io.containerd.kata.v2"
        privileged_without_host_devices = true
        pod_annotations = ["io.katacontainers.*"]
      [plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.kata.options]
        ConfigPath = "${kataConfig}"
    '';
  };

  # containerd resolves `io.containerd.kata.v2` to containerd-shim-kata-v2 on its PATH.
  systemd.services.k3s.path = [ pkgs.kata-runtime ];

  boot.kernelModules = [ "vhost_vsock" ];

  networking.firewall = {
    trustedInterfaces = [
      "cni0"
      "flannel.1"
    ];
    # Pod traffic leaves through flannel and returns on the LAN interface.
    checkReversePath = "loose";
    extraCommands = lib.concatMapStrings (ip: ''
      iptables -A nixos-fw -s ${ip} -p tcp --dport 10250 -j nixos-fw-accept
      iptables -A nixos-fw -s ${ip} -p udp --dport 8472 -j nixos-fw-accept
    '') servers;
  };
}
