{
  pkgs,
  self,
}:
let
  inherit (pkgs) lib;

  build-config = import ./build-config.nix pkgs;

  local-version =
    with builtins;
    let
      flakever = self.shortRev or "dev";

      symver = lib.pipe (readFile ../CHANGELOG) [
        (split "\n")
        (filter (x: !isList x && lib.strings.hasPrefix "Qtile" x))
        (release: elemAt release 1) # the 0th element is the template
        (match "Qtile ([0-9.]+), released ([0-9-]+):")
        head
      ];
    in
    "${symver}+${flakever}.flake";

  qtile-override-func =
    qtile-prev:
    {
      name = "${qtile-prev.pname}-${qtile-prev.version}";

      version = local-version;

      src = ./..; # use the source of the git repo
    }
    // {
      env = build-config.resolved-env-vars;

      pypaBuildFlags = [ "--config-setting=backend=wayland" ] ++ build-config.resolved-config-settings;
    }
    // {
      # removes nixpkgs patching, as we handle it locally
      postPatch = "";

      patches = [ ];

      # qtile-wayland.desktop has been removed; the same qtile.desktop now works
      # for both backends, so install it to both session directories
      postInstall = ''
        install resources/qtile.desktop -Dt $out/share/xsessions
        install resources/qtile.desktop -Dt $out/share/wayland-sessions
      '';
    };
in
(pkgs.python3Packages.qtile.overrideAttrs qtile-override-func).override {
  wlroots = pkgs.wlroots_0_20;
}
