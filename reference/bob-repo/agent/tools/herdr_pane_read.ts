import { defineTool } from "eve/tools";
import { z } from "zod";
import { hostExec, herdrBin } from "../lib/host-exec.js";

// SCOPING CHOICE (RFC S6): one herdr tool, not the full herdr surface - only
// the one call spawn-team.md's drive loop actually issues for "read a
// stalled pane's recent output" (RFC S6's own example). Confirmed against
// the real source once it landed in this clone (docs/reference/commands/
// spawn-team.md, closing line): "If a pane's agent never reaches ready,
// read it with `herdr pane read <pane> --source recent` to see why before
// retrying." This supersedes two earlier guesses in this file's history:
// `herdr pane output <pane>` (unevidenced) and `herdr wait output <pane>
// --match ... --timeout ...` (real, but it is spawn.py's own ready/working
// marker wait, not the stalled-pane read spawn-team.md means - it blocks
// for a pattern rather than dumping what is already on screen).
//
// Out of scope for this one tool, and WHY each stays out:
// - `herdr wait output <pane> --match ... --timeout ...`: spawn.py-internal
//   (launch()/submit()'s own ready/working marker wait) - spawn-team.md
//   never issues this call itself.
// - `herdr wait agent-status <pane> --status done`: spawn-team.md's step-4
//   drive-loop call, but it is a POLL for a lead to finish - and in the eve
//   L1 model that poll is SUBSUMED by the push inbound-turn model (RFC S5's
//   direction-inversion): a lead's reply/progress/handoff arrives as an
//   ordinary inbound room turn, the same reason `orbal-net recv` itself has
//   no tool wrapper. Only ORIGINATING/diagnostic herdr calls stay as tools
//   here; blocking-wait calls collapse into the turn model instead. This is
//   an RFC-grounded boundary, not a "one tool for minimalism" cutoff - an
//   earlier round of this file briefly added a sibling
//   herdr_wait_agent_status tool and then withdrew it for exactly this
//   reason.
const inputSchema = z.object({
  pane: z.string().min(1),
});

// herdr pane read <pane> --source recent - argv byte-for-byte against
// docs/reference/commands/spawn-team.md.
export function buildArgv(input: z.infer<typeof inputSchema>): string[] {
  return ["pane", "read", input.pane, "--source", "recent"];
}

export default defineTool({
  description:
    "Read a pane's recent output without waiting (herdr pane read <pane> --source recent) - for checking why a lead/worker's agent never reached ready, or why it looks stalled.",
  inputSchema,
  async execute(input) {
    return hostExec(herdrBin(), buildArgv(input));
  },
});
