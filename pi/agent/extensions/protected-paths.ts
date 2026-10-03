/**
 * Protected Paths Extension
 *
 * Blocks write/edit operations to sensitive files and directories.
 * Prevents accidental modification of env files, git internals, etc.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  const protectedPaths = [
    ".env",
    ".git/",
    "node_modules/",
    ".next/",
    "dist/",
    "build/",
    "bun.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "skills-lock.json",
    ".pi/settings.json",
    ".pi/agent/settings.json",
  ];

  pi.on("tool_call", async (event, ctx) => {
    if (event.toolName !== "write" && event.toolName !== "edit") return undefined;

    const path = event.input.path as string;
    const isProtected = protectedPaths.some((p) => path.includes(p));

    if (isProtected) {
      if (ctx.hasUI) {
        ctx.ui.notify(`Blocked write to protected path: ${path}`, "warning");
      }
      return { block: true, reason: `Path "${path}" is protected. Edit settings or .env files manually.` };
    }

    return undefined;
  });
}
