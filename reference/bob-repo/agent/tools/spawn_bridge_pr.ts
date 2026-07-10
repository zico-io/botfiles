import { defineTool } from "eve/tools";
import { z } from "zod";
import { hostExec, python3Bin, spawnPyPath } from "../lib/host-exec.js";
import { consumeConfirmation, requestConfirmation } from "../lib/confirm-gate.js";

const ACTION = "spawn_bridge_pr";

const inputSchema = z.object({
  feature: z.string().min(1),
  title: z.string().optional().describe("PR title; spawn.py falls back to --fill when omitted"),
  confirm_token: z
    .string()
    .optional()
    .describe("Token from a prior confirmation challenge for this exact call; omit on the first call"),
});

// spawn.py bridge-pr <feature> [title] - argv byte-for-byte per RFC S6.
export function buildArgv(input: { feature: string; title?: string }): string[] {
  const args = ["bridge-pr", input.feature];
  if (input.title !== undefined) args.push(input.title);
  return args;
}

// GATED (RFC S6): a live, irreversible, externally-visible GitHub write (a
// real push plus a real PR) - the human-in-the-loop property must be
// preserved. eve/tools/approval `always()` CANNOT be used here: vercel/eve
// #533 - an approval:always() tool's approve-resume re-invokes the model
// with the tool's tool_use block but no matching tool_result, so Anthropic
// 400s on the dangling tool_use and the session dies before the approved
// tool ever runs. Not fixable in bob; a version bump does not help either
// (0.22.4 has the same bug).
//
// Instead this tool gates itself with a two-phase conversational confirm
// (agent/lib/confirm-gate.ts) riding eve's ordinary turn loop: the FIRST
// call (no confirm_token) has no side effect and returns a single-use token
// tied to this exact (action, args); only a SECOND call carrying that exact
// token runs the push+PR. No single model call can fire the side effect - a
// human turn supplying the token back is structurally required in between.
// Revert to approval: always() (and drop this gate) once #533's out-of-band
// approval-resume path is fixed upstream.
export default defineTool({
  description:
    "Push a mission's branch and open its GitHub PR (spawn.py bridge-pr <feature> [title]). Spawned leads/workers are air-gapped (no gh, no network); this is the harvest-then-push ceremony done on their behalf. Live GitHub write - the first call returns a confirmation challenge and does NOT act; call again with the human-confirmed confirm_token to run it.",
  inputSchema,
  async execute(input) {
    const { confirm_token, ...args } = input;
    if (!confirm_token) {
      const { token, challenge } = requestConfirmation(ACTION, args);
      return { confirmation_required: true, token, challenge };
    }
    const v = consumeConfirmation(ACTION, args, confirm_token);
    if (!v.ok) {
      return { confirmed: false, error: `confirmation refused: ${v.reason}` };
    }
    return hostExec(python3Bin(), [spawnPyPath(), ...buildArgv(args)]);
  },
});
