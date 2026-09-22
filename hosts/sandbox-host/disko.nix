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
            mountpoint = "/var/lib/microsandbox";
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
            mountpoint = "/var/cache/sandbox";
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
