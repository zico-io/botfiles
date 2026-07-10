// Two-phase conversational confirmation gate for irreversible tools
// (spawn_bridge_pr, spawn_down). Replaces eve/tools/approval `always()`,
// which cannot be used for these tools: vercel/eve #533 - an approval:
// always() tool, on approve, has eve re-invoke the model with the tool's
// tool_use block but NO matching tool_result, producing a dangling tool_use
// that Anthropic 400s on, so the approved tool never runs and the session
// dies. Not fixable in bob; the fix must land upstream.
//
// The gate instead rides eve's ordinary turn loop: a tool's FIRST call
// (no confirm_token) has NO side effect and returns a single-use token bound
// to the exact (action, args) pair; the SAME tool's SECOND call, carrying
// that exact token, runs the side effect. No single model call can fire the
// side effect - a human turn supplying the token back is structurally
// required in between.
//
// No em dashes - use "-".

import { createHash, randomBytes } from "node:crypto";

const TTL_MS = 15 * 60_000;

interface PendingConfirmation {
  action: string;
  argsHash: string;
  expiresAt: number;
}

const pending = new Map<string, PendingConfirmation>();

// Deterministic JSON with sorted keys, so the same args always hash the same
// way regardless of property insertion order.
function stableStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map((v) => stableStringify(v)).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    const keys = Object.keys(value as Record<string, unknown>).sort();
    return `{${keys
      .map((k) => `${JSON.stringify(k)}:${stableStringify((value as Record<string, unknown>)[k])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function hashArgs(args: unknown): string {
  return createHash("sha256").update(stableStringify(args)).digest("hex");
}

// Opportunistically drop expired entries so the map does not grow unbounded
// across a long-lived session.
function pruneExpired(now: number): void {
  for (const [token, entry] of pending) {
    if (entry.expiresAt <= now) pending.delete(token);
  }
}

export interface ConfirmationChallenge {
  token: string;
  challenge: string;
}

// Issues a single-use confirmation token for (action, args). No side effect.
export function requestConfirmation(action: string, args: unknown): ConfirmationChallenge {
  const now = Date.now();
  pruneExpired(now);
  const token = randomBytes(16).toString("hex");
  pending.set(token, { action, argsHash: hashArgs(args), expiresAt: now + TTL_MS });
  const challenge =
    `Confirm ${action}(${stableStringify(args)})? Reply with the token to run it: ${token}`;
  return { token, challenge };
}

export type ConfirmationFailureReason =
  | "no-token"
  | "unknown-token"
  | "wrong-action"
  | "args-mismatch"
  | "expired";

export type ConfirmationResult = { ok: true } | { ok: false; reason: ConfirmationFailureReason };

// Consumes a confirmation token for (action, args). Single-use: on success
// the entry is deleted, so the same token can never confirm again.
export function consumeConfirmation(
  action: string,
  args: unknown,
  token: string,
): ConfirmationResult {
  if (!token) return { ok: false, reason: "no-token" };
  const now = Date.now();
  // Check this token's own expiry BEFORE the opportunistic sweep below -
  // otherwise the sweep would delete an expired entry first and this would
  // report the less specific "unknown-token" instead of "expired".
  const entry = pending.get(token);
  pruneExpired(now);
  if (!entry) return { ok: false, reason: "unknown-token" };
  if (entry.expiresAt <= now) {
    pending.delete(token);
    return { ok: false, reason: "expired" };
  }
  if (entry.action !== action) return { ok: false, reason: "wrong-action" };
  if (entry.argsHash !== hashArgs(args)) return { ok: false, reason: "args-mismatch" };
  pending.delete(token);
  return { ok: true };
}
