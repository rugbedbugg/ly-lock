{
  lib,
  python3Packages,
  wrapGAppsHook4,
  gobject-introspection,
  gtk4,
  gtk4-layer-shell,
}:

python3Packages.buildPythonApplication {
  pname = "ly-lock";
  version = "0.1.1";
  src = lib.cleanSource ../.;
  pyproject = true;

  build-system = [ python3Packages.setuptools ];

  nativeBuildInputs = [
    wrapGAppsHook4
    gobject-introspection
  ];

  buildInputs = [
    gtk4
    gtk4-layer-shell
  ];

  dependencies = with python3Packages; [
    numpy
    pygobject3
    pyopengl
    python-pam
  ];

  nativeCheckInputs = [ python3Packages.pytestCheckHook ];

  # Wrap once, with both the GApps and the Python environment.
  dontWrapGApps = true;
  preFixup = ''
    makeWrapperArgs+=(
      "''${gappsWrapperArgs[@]}"
      --set LY_LOCK_LAYER_SHELL ${gtk4-layer-shell}/lib/libgtk4-layer-shell.so.0
    )
  '';

  postInstall = ''
    install -Dm644 pam/ly-lock $out/etc/pam.d/ly-lock
  '';

  pythonImportsCheck = [ "ly_lock" ];

  meta = {
    description = "Wayland lock screen that looks and behaves like the ly display manager";
    homepage = "https://github.com/rugbedbugg/ly-lock";
    license = lib.licenses.wtfpl;
    mainProgram = "ly-lock";
    platforms = lib.platforms.linux;
  };
}
