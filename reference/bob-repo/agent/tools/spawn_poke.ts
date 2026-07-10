import { defineTool } from "eve/tools";
import { z } from "zod";
import { hostExec, python3Bin, spawnPyPath } from "../lib/host-exec.js";

const inputSchema = z.object({
  feature: z.string().min(1),
  role: z.string().min(1),
  message: z
    .string()
    .optional()
    .describe("Optional nudge text; spawn.py uses a default prompt when omitted"),
});

// spawn.py poke <feature> <role> [msg] - argv byte-for-byte per RFC S6.
export function buildArgv(input: z.infer<typeof inputSchema>): string[] {
  const args = ["poke", input.feature, input.role];
  if (input.message !== undefined) args.push(input.message);
  return args;
}

export default defineTool({
  description:
    "Nudge a pane idle between orbal-net recv calls (spawn.py poke <feature> <role> [msg]). Still needed for any local-TUI lead/worker regardless of whether L1 is bob or claude.",
  inputSchema,
  async execute(input) {
    return hostExec(python3Bin(), [spawnPyPath(), ...buildArgv(input)]);
  },
});
