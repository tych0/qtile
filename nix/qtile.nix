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

      postInstall = ''
        install resources/qtile.desktop -Dt $out/share/xsessions
        install resources/qtile.desktop -Dt $out/share/wayland-sessions
        install -Dm644 resources/qtile.service \
          $out/share/systemd/user/qtile.service
        install -Dm644 resources/qtile-session.target \
          $out/share/systemd/user/qtile-session.target

        substituteInPlace $out/share/systemd/user/qtile.service \
          --replace-fail '%h/.local/bin/qtile' '${placeholder "out"}/bin/qtile' \
          --replace-fail '/usr/bin/systemctl' '${pkgs.systemd}/bin/systemctl'
      '';
    }
    // {
      # bound hanging tests with pytest-timeout (buildPythonPackage runs its
      # tests in the install check phase, so this must be
      # nativeInstallCheckInputs; a nativeCheckInputs override is silently
      # ignored). NB: pytest-forked is deliberately absent: it needs the real
      # 'py' library, which pytest >= 9's vendored 'py' shim shadows here, so
      # its isolation forks crash ("module 'py' has no attribute 'process'").
      # The suite registers the 'forked' marker, so those tests degrade to
      # running unforked, as they always have in this environment.
      nativeInstallCheckInputs =
        (qtile-prev.nativeInstallCheckInputs or [ ]) ++ (with pkgs.python3Packages; [ pytest-timeout ]);
    };
in
(pkgs.python3Packages.qtile.overrideAttrs qtile-override-func).override {
  wlroots = pkgs.wlroots_0_20;
}
