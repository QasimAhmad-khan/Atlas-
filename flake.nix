{
  description = "AtlasPipe development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
  };

  outputs =
    { nixpkgs, ... }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      devShells = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        {
          default = pkgs.mkShell {
            packages = [
              pkgs.git
              pkgs.postgresql_16
              pkgs.python312
            ];

            shellHook = ''
              echo "AtlasPipe dev shell"
              echo "Run: python -m venv .venv && source .venv/bin/activate"
              echo "Then: python -m pip install -e '.[dev]' && python -m pytest"
            '';
          };
        }
      );
    };
}
