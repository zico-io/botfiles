{
  description = "botfiles - agent memory SSOT, dev toolchain, and the sandbox-host NixOS guest";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    disko = {
      url = "github:nix-community/disko";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    sops-nix = {
      url = "github:Mic92/sops-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    home-manager = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    # No nixpkgs follows: its own pin is what cache.numtide.com built against,
    # so following ours would turn every agent CLI into a local build.
    llm-agents.url = "github:numtide/llm-agents.nix";
  };

  outputs =
    {
      self,
      nixpkgs,
      disko,
      sops-nix,
      home-manager,
      llm-agents,
    }:
    let
      # Hand-rolled instead of flake-utils: one fewer input for one genAttrs.
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      # msb is a KVM runtime, so it is Linux-only. On macOS the sandbox layer is
      # Apple `container` (sandbox/build.sh), not this.
      packages = forAllSystems (
        pkgs:
        let
          msb = pkgs.callPackage ./pkgs/microsandbox.nix { };
        in
        nixpkgs.lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
          microsandbox = msb;
          default = msb;
        }
      );

      devShells = forAllSystems (pkgs: {
        default = import ./nix/shell.nix { inherit pkgs; };
      });

      checks = forAllSystems (
        pkgs:
        import ./nix/checks.nix {
          inherit pkgs;
          src = self;
        }
      );

      formatter = forAllSystems (pkgs: pkgs.nixfmt);

      nixosModules = {
        microsandbox = import ./modules/microsandbox.nix;
        tailnet = import ./modules/tailnet.nix;
      };

      nixosConfigurations.sandbox-host = nixpkgs.lib.nixosSystem {
        system = "x86_64-linux";
        modules = [
          disko.nixosModules.disko
          sops-nix.nixosModules.sops
          home-manager.nixosModules.home-manager
          self.nixosModules.microsandbox
          self.nixosModules.tailnet
          {
            nixpkgs.overlays = [
              (final: prev: { llm-agents = llm-agents.packages.${prev.stdenv.hostPlatform.system}; })
            ];
          }
          ./hosts/sandbox-host
        ];
      };
    };
}
