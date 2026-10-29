# Declarative disk layout for the sandbox-host VM.
#
# Four VirtIO disks so OS state, workspace churn, dependency cache, and durable
# artifacts have separate lifecycle and failure boundaries. ext4 on top of ZFS
# zvols is deliberate: integrity, compression, and snapshots already live in the
# pool below the VM, and a second copy-on-write layer inside the guest would
# only cost write amplification.
{
  disko.devices.disk = {
    os = {
      device = "/dev/vda";
      type = "disk";
      content = {
        type = "gpt";
        partitions = {
          ESP = {
            size = "1G";
            type = "EF00";
            content = {
              type = "filesystem";
              format = "vfat";
              mountpoint = "/boot";
              mountOptions = [ "umask=0077" ];
            };
          };
          root = {
            size = "100%";
            content = {
              type = "filesystem";
              format = "ext4";
              mountpoint = "/";
            };
          };
        };
      };
    };

    work = {
      device = "/dev/vdb";
      type = "disk";
      content = {
        type = "gpt";
        partitions.work = {
          size = "100%";
          content = {
            type = "filesystem";
            format = "ext4";
            # Persistent sandbox homes: yggdrasil's local-path provisioner for
            # the `local-sandbox` StorageClass roots its volumes here.
            mountpoint = "/var/lib/sandboxes";
            mountOptions = [ "noatime" ];
          };
        };
      };
    };

    cache = {
      device = "/dev/vdc";
      type = "disk";
      content = {
        type = "gpt";
        partitions.cache = {
          size = "100%";
          content = {
            type = "filesystem";
            format = "ext4";
            # containerd's image store. The kubelet clears images when the
            # filesystem holding them fills, so on / anything else written there
            # evicted the CI and sandbox images and every job pulled them again.
            mountpoint = "/var/lib/rancher/k3s/agent/containerd";
            mountOptions = [ "noatime" ];
          };
        };
      };
    };

    artifacts = {
      device = "/dev/vdd";
      type = "disk";
      content = {
        type = "gpt";
        partitions.artifacts = {
          size = "100%";
          content = {
            type = "filesystem";
            format = "ext4";
            mountpoint = "/var/lib/sandbox-artifacts";
            mountOptions = [ "noatime" ];
          };
        };
      };
    };
  };
}
