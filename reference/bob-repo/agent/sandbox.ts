import { defineSandbox } from "eve/sandbox";
import { microsandbox } from "eve/sandbox/microsandbox";

// Pin the microsandbox sandbox backend explicitly.
//
// Without a pin, eve falls back to defaultBackend(), which on macOS Apple
// Silicon resolves to microsandbox anyway (Vercel -> Docker -> microsandbox ->
// just-bash) but does NOT install it: the microsandbox package + VM runtime are
// not bundled, and `eve start` (production) fails at sandbox prewarm with an
// install error instead of auto-installing (only `eve dev` auto-installs). The
// in-VM proofs never hit this because the Linux mission VM resolved the default
// differently. We install the `microsandbox` package as a devDependency and pin
// microsandbox() so `eve start` boots deterministically.
//
// microsandbox runs each sandbox in a lightweight local VM with real binaries
// (git/node/npm) - the closest local match to hosted Vercel Sandbox, and unlike
// just-bash it can actually run the coding tools' commands. Supported on macOS
// Apple Silicon and glibc Linux with KVM.
// setup.autoInstall lets eve install the microsandbox VM runtime (libkrun) on
// first boot if it is missing, instead of failing at prewarm - so a fresh host
// self-heals rather than needing a manual runtime install step.
export default defineSandbox({ backend: microsandbox({ setup: { autoInstall: true } }) });
