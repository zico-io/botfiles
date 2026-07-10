import { defineTool } from "eve/tools";
import { z } from "zod";
import { detachRoom } from "../lib/connector-control.js";
import { hostExec, python3Bin, spawnPyPath } from "../lib/host-exec.js";
import { consumeConfirmation, requestConfirmation } from "../lib/confirm-gate.js";

const ACTION = "spawn_down";

const inputSchema = z.object({
  feature: z.string().min(1),
  confirm_token: z
    .string()
    .optional()
    .describe("Token from a prior confirmation challenge for this exact call; omit on the first call"),
});

// spawn.py down <feature> - argv byte-for-byte per RFC S6.
export function buildArgv(input: { feature: string }): string[] {
  return ["down", input.feature];
}

// GATED (RFC S6): mission teardown kills every pane/VM for the mission and
// the orbal-net server dies with it - the rooms go with it. Hard to reverse,
// so human-in-the-loop is required. eve/tools/approval `always()` CANNOT be
// used here: vercel/eve #533 - an approval:always() tool's approve-resume
// re-invokes the model with the tool's tool_use block but no matching
// tool_result, so Anthropic 400s on the dangling tool_use and the session
// dies before the approved tool ever runs. Not fixable in bob; a version
// bump does not help either (0.22.4 has the same bug).
//
// Instead this tool gates itself with a two-phase conversational confirm
// (agent/lib/confirm-gate.ts) riding eve's ordinary turn loop: the FIRST
// call (no confirm_token) has no side effect and returns a single-use token
// tied to this exact (action, args); only a SECOND call carrying that exact
// token runs the teardown. No single model call can fire the side effect - a
// human turn supplying the token back is structurally required in between,
// mirroring AGENTS.md's "always confirm first" norm. Revert to
// approval: always() (and drop this gate) once #533's out-of-band
// approval-resume path is fixed upstream.
export default defineTool({
  description:
    "Tear down a mission fleet (spawn.py down <feature>): kills every pane/VM and the mission's orbal-net server, so mission-<feature> and every squad-<lead> room die with it. Detaches bob's connector from mission-<feature> first (RFC S8). Irreversible - the first call returns a confirmation challenge and does NOT act; call again with the human-confirmed confirm_token to run it.",
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
    const room = `mission-${args.feature}`;
    // Detach BEFORE spawn.py down, while the mission's orbal-net server is
    // still alive - removing the connector's stream first avoids a
    // teardown-time stream error (RFC S8). A detach failure must not block
    // teardown itself, so it is caught and surfaced as a warning, not thrown.
    let detached = true;
    let warning: string | undefined;
    try {
      await detachRoom(room);
    } catch (err) {
      detached = false;
      warning = `connector detach for ${room} failed, proceeding with teardown anyway: ${err instanceof Error ? err.message : String(err)}`;
    }
    const result = await hostExec(python3Bin(), [spawnPyPath(), ...buildArgv(args)]);
    return { down: result.stdout, detached, room, ...(warning ? { warning } : {}) };
  },
});
