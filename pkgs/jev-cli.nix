# jev-cli (`jev`) - typed noul/choice/score judgments from TypeSafe Jev, cheap
# enough to sit inside an agent loop. Not in nixpkgs.
#
# Only the CLI ships. Upstream's `jev-mcp` needs mcp>=2.2, whose httpx2 and
# mcp-types dependencies nixpkgs does not carry; the CLI itself is stdlib-only.
#
# With apiKeyFile set, the wrapper exports TYPESAFE_API_KEY from it unless the
# caller already set one, so a sops secret works without a per-login
# `jev auth set`.
{
  lib,
  python313Packages,
  fetchPypi,
  apiKeyFile ? null,
}:

python313Packages.buildPythonApplication rec {
  pname = "jev-cli";
  version = "0.7.0";
  pyproject = true;

  src = fetchPypi {
    pname = "jev_cli";
    inherit version;
    hash = "sha256-5NVcTXn8ffibWf6klF9CzzuwMcveUdzuK+74vQ0Rc44=";
  };

  # Upstream caps uv_build below the 0.10 nixpkgs ships; the build is plain.
  postPatch = ''
    substituteInPlace pyproject.toml \
      --replace-fail 'uv_build>=0.8.15,<0.9.0' 'uv_build>=0.8.15' \
      --replace-fail 'jev-mcp = "jev_cli.mcp_server:main"' ""
    rm src/jev_cli/mcp_server.py
  '';

  build-system = [ python313Packages.uv-build ];

  pythonRemoveDeps = [ "mcp" ];

  # Agent skill roots link here instead of into site-packages.
  postInstall = ''
    mkdir -p $out/share/skills
    ln -s $out/${python313Packages.python.sitePackages}/jev_cli/bundled_skills/jev-cli $out/share/skills/jev-cli
  '';

  # wrapPythonPrograms evals these as a bash array, hence the escaping.
  makeWrapperArgs = lib.optionals (apiKeyFile != null) [
    "--run"
    (lib.escapeShellArg ''
      if [ -z "''${TYPESAFE_API_KEY:-}" ] && [ -r ${apiKeyFile} ]; then
        TYPESAFE_API_KEY="$(< ${apiKeyFile})"
        export TYPESAFE_API_KEY
      fi'')
  ];

  pythonImportsCheck = [ "jev_cli" ];

  doInstallCheck = true;
  installCheckPhase = ''
    runHook preInstallCheck
    $out/bin/jev --version | grep -qx 'jev ${version}'
    runHook postInstallCheck
  '';

  meta = {
    description = "CLI for TypeSafe Jev typed judgments";
    homepage = "https://github.com/tumf/jev-cli";
    license = lib.licenses.mit;
    mainProgram = "jev";
  };
}
