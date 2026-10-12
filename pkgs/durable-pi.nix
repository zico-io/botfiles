# Durable Pi: the dpi-backend device server and the playground hub + web UI,
# run from source with tsx the way the repo runs them. Not in nixpkgs.
#
# Each app keeps its own package-lock.json, so node_modules come from three
# importNpmLock builds (no npmDepsHash to bump) and are copied next to their
# app: the hub and backend import ../dpi-sdk by relative path, and dpi-sdk
# resolves `yaml` from its own node_modules.
{
  lib,
  stdenv,
  importNpmLock,
  nodejs_24,
  src,
}:

let
  modules =
    app:
    importNpmLock.buildNodeModules {
      npmRoot = "${src}/apps/${app}";
      nodejs = nodejs_24;
    };
  apps = [
    "dpi-sdk"
    "dpi-playground"
    "dpi-backend"
  ];
in
stdenv.mkDerivation {
  pname = "durable-pi";
  version = "0-unstable-${src.shortRev or "dirty"}";
  inherit src;

  nativeBuildInputs = [ nodejs_24 ];

  postPatch = lib.concatMapStrings (app: ''
    cp -r ${modules app}/node_modules apps/${app}/
    chmod -R u+w apps/${app}/node_modules
  '') apps;

  # The playground is one Next.js app (hub routes and web UI); the hub serves .next at runtime.
  buildPhase = ''
    runHook preBuild
    export HOME=$TMPDIR NEXT_TELEMETRY_DISABLED=1
    (cd apps/dpi-playground && node node_modules/next/dist/bin/next build)
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    mkdir -p $out/share/durable-pi/apps
    cp -r ${lib.concatMapStringsSep " " (app: "apps/${app}") apps} $out/share/durable-pi/apps/
    runHook postInstall
  '';

  passthru = {
    nodejs = nodejs_24;
    root = "share/durable-pi/apps";
  };

  meta = {
    description = "Durable Agent Network: dpi-backend device server and playground hub";
    homepage = "https://github.com/zico-io/durable-pi";
    license = lib.licenses.mit;
    platforms = lib.platforms.unix;
  };
}
