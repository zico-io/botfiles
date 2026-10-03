/**
 * Confirm Destructive Actions Extension
 *
 * Prompts for confirmation before destructive session actions
 * (new, switch). Prevents accidental data loss.
 */

import type { ExtensionAPI, SessionBeforeSwitchEvent, SessionMessageEntry } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  pi.on("session_before_switch", async (event: SessionBeforeSwitchEvent, ctx) => {
    if (!ctx.hasUI) return;

    if (event.reason === "new") {
      const confirmed = await ctx.ui.confirm(
        "Clear session?",
        "This will delete all messages in the current session.",
      );
      if (!confirmed) {
        ctx.ui.notify("Clear cancelled", "info");
        return { cancel: true };
      }
      return;
    }

    // For resume: check if there are unsaved messages
    const entries = ctx.sessionManager.getEntries();
    const hasUnsavedWork = entries.some(
      (e): e is SessionMessageEntry => e.type === "message" && e.message.role === "user",
    );

    if (hasUnsavedWork) {
      const confirmed = await ctx.ui.confirm(
        "Switch session?",
        "You have messages in the current session. Switch anyway?",
      );
      if (!confirmed) {
        ctx.ui.notify("Switch cancelled", "info");
        return { cancel: true };
      }
    }
  });

}
