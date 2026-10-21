{
  description = "Wayland lock screen that looks and behaves like the ly display manager";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAll (pkgs: rec {
        ly-lock = pkgs.callPackage ./nix/package.nix { };
        default = ly-lock;
      });

      overlays.default = final: _prev: {
        ly-lock = final.callPackage ./nix/package.nix { };
      };

      nixosModules.default = ./nix/module.nix;

      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          inputsFrom = [ self.packages.${pkgs.stdenv.hostPlatform.system}.ly-lock ];
          packages = [
            pkgs.python3Packages.pytest
            pkgs.ruff
          ];
        };
      });

      formatter = forAll (pkgs: pkgs.nixfmt);
    };
}
