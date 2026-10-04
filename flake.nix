{
  description = "botfiles - shared tooling and instructions for the remote T3 Code server";

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
      packages = forAllSystems (
        pkgs:
        let
          msb = pkgs.callPackage ./pkgs/microsandbox.nix { };
          botfiles = pkgs.callPackage ./pkgs/botfiles.nix { src = self; };
        in
        {
          inherit botfiles;
          default = botfiles;
          t3code = llm-agents.packages.${pkgs.stdenv.hostPlatform.system}.t3code.override {
            providerPackages = with llm-agents.packages.${pkgs.stdenv.hostPlatform.system}; [
              claude-code
              codex
            ];
          };
        }
        # msb needs KVM and is available only on Linux.
        // nixpkgs.lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
          microsandbox = msb;
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
              (final: prev: {
                llm-agents = llm-agents.packages.${prev.stdenv.hostPlatform.system};
                t3code = self.packages.${prev.stdenv.hostPlatform.system}.t3code;
                botfiles = self.packages.${prev.stdenv.hostPlatform.system}.botfiles;
              })
            ];
          }
          ./hosts/sandbox-host
        ];
      };
    };
}
