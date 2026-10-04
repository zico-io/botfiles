{
  lib,
  runCommand,
  makeWrapper,
  python3,
  bash,
  src,
}:

runCommand "botfiles" { nativeBuildInputs = [ makeWrapper ]; } ''
  mkdir -p $out/share/botfiles $out/bin
  for path in AGENTS.md .botfile bin skills toolbox provision.sh linear-skills.lock.json; do
    cp -r ${src}/$path $out/share/botfiles/$path
  done
  for tool in botfile toolbox sync-skills; do
    makeWrapper ${lib.getExe python3} $out/bin/$tool \
      --add-flags "$out/share/botfiles/bin/$tool"
  done
  makeWrapper ${lib.getExe bash} $out/bin/botfiles-provision \
    --add-flags "$out/share/botfiles/provision.sh" \
    --set BOTFILES_TOOLBOX "$out/bin/toolbox" \
    --prefix PATH : ${lib.makeBinPath [ python3 ]}
''
