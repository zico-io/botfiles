# microsandbox (`msb`) - the local-first microVM runtime the sandbox-host runs.
# Not in nixpkgs, so this packages upstream's release archive.
#
# Upstream ships one flat tarball per platform holding exactly two files: the
# `msb` binary and the matching libkrunfw shared object. `msb` does NOT list
# libkrunfw in its ELF NEEDED entries (it dlopens it by SONAME) and its stock
# RUNPATH ships a literally-escaped `\$$ORIGIN`, which the loader cannot expand,
# so appendRunpaths below is what actually makes the pair resolve.
{
  lib,
  stdenv,
  fetchurl,
  autoPatchelfHook,
  libcap-ng,
}:

let
  version = "0.7.2";

  # Hashes are upstream's published checksums.sha256 for the tag. The
  # x86_64 archive was additionally downloaded and byte-verified against it.
  sources = {
    x86_64-linux = {
      asset = "microsandbox-linux-x86_64.tar.gz";
      hash = "sha256-R8Ij4+9SmKvwX0ftn4eYEQbkANmbs/HQQtTWiBNGsYs=";
    };
    aarch64-linux = {
      asset = "microsandbox-linux-aarch64.tar.gz";
      hash = "sha256-1N54FBR7g1pLmeUeI2yLMzNACR5XJ6C0XX64R9VrAio=";
    };
  };

  source =
    sources.${stdenv.hostPlatform.system}
      or (throw "microsandbox: no upstream release asset for ${stdenv.hostPlatform.system}");
in
stdenv.mkDerivation {
  pname = "microsandbox";
  inherit version;

  src = fetchurl {
    url = "https://github.com/superradcompany/microsandbox/releases/download/v${version}/${source.asset}";
    inherit (source) hash;
  };

  # The archive has no top-level directory.
  sourceRoot = ".";

  nativeBuildInputs = [ autoPatchelfHook ];
  buildInputs = [
    libcap-ng
    stdenv.cc.cc.lib
  ];

  appendRunpaths = [ "${placeholder "out"}/lib" ];

  installPhase = ''
    runHook preInstall

    install -Dm755 msb -t $out/bin

    krunfw=$(echo libkrunfw.so.*)
    install -Dm755 "$krunfw" -t $out/lib
    ln -s "$out/lib/$krunfw" "$out/lib/$(patchelf --print-soname "$krunfw")"
    ln -s "$out/lib/$krunfw" "$out/lib/libkrunfw.so"

    runHook postInstall
  '';

  # Proves the patched binary actually loads before anything deploys it.
  # HOME is redirected because msb resolves MSB_HOME from it.
  doInstallCheck = true;
  installCheckPhase = ''
    runHook preInstallCheck
    export HOME=$(mktemp -d)
    $out/bin/msb --help > /dev/null
    runHook postInstallCheck
  '';

  meta = {
    description = "Local-first microVM sandbox runtime for agent workloads";
    homepage = "https://microsandbox.dev";
    license = lib.licenses.asl20;
    mainProgram = "msb";
    platforms = lib.attrNames sources;
    sourceProvenance = [ lib.sourceTypes.binaryNativeCode ];
  };
}
