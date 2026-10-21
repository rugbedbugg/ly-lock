{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.programs.ly-lock;
in
{
  options.programs.ly-lock = {
    enable = lib.mkEnableOption "ly-lock, a lock screen that matches the ly display manager";
    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ./package.nix { };
      defaultText = lib.literalExpression "ly-lock";
      description = "The ly-lock package to use.";
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ cfg.package ];
    security.pam.services.ly-lock = { };
  };
}
