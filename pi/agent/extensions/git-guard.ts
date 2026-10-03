/**
 * Git Guard Extension
 *
 * Two features:
 * 1. Warns before session changes when there are uncommitted git changes
 * 2. Creates git stash checkpoints at each turn for /fork rollback
 */

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

async function checkDirtyRepo(
  pi: ExtensionAPI,
  ctx: ExtensionContext,
  action: string,
): Promise<{ cancel: boolean } | undefined> {
  const { stdout, code } = await pi.exec("git", ["status", "--porcelain"]);

  if (code !== 0) return; // Not a git repo, allow
  if (stdout.trim().length === 0) return; // Clean repo, allow

  if (!ctx.hasUI) return { cancel: true };

  const changedFiles = stdout.trim().split("\n").filter(Boolean).length;
  const choice = await ctx.ui.select(
    `You have ${changedFiles} uncommitted file(s). ${action} anyway?`,
    ["Yes, proceed anyway", "No, let me commit first"],
  );

  if (choice !== "Yes, proceed anyway") {
    ctx.ui.notify("Commit your changes first", "warning");
    return { cancel: true };
  }
}

export default function (pi: ExtensionAPI) {
  // --- Git stash checkpoints for /fork rollback ---
  const checkpoints = new Map<string, string>();
  let currentEntryId: string | undefined;

  pi.on("tool_result", async (_event, ctx) => {
    const leaf = ctx.sessionManager.getLeafEntry();
    if (leaf) currentEntryId = leaf.id;
  });

  pi.on("turn_start", async () => {
    const { stdout } = await pi.exec("git", ["stash", "create"]);
    const ref = stdout.trim();
    if (ref && currentEntryId) {
      checkpoints.set(currentEntryId, ref);
    }
  });

  pi.on("session_before_fork", async (event, ctx) => {
    const ref = checkpoints.get(event.entryId);
    if (!ref) return;
    if (!ctx.hasUI) return;

    const choice = await ctx.ui.select("Restore code state?", [
      "Yes, restore code to that point",
      "No, keep current code",
    ]);

    if (choice?.startsWith("Yes")) {
      await pi.exec("git", ["stash", "apply", ref]);
      ctx.ui.notify("Code restored to checkpoint", "info");
    }
  });

  pi.on("agent_end", async () => {
    checkpoints.clear();
  });

  // --- Dirty repo guard for session changes ---
  pi.on("session_before_switch", async (event, ctx) => {
    const action = event.reason === "new" ? "new session" : "switch session";
    return checkDirtyRepo(pi, ctx, action);
  });

  pi.on("session_before_fork", async (_event, ctx) => {
    return checkDirtyRepo(pi, ctx, "fork");
  });
}
