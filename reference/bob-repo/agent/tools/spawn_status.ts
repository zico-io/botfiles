import { defineTool } from "eve/tools";
import { z } from "zod";
import { hostExec, python3Bin, spawnPyPath } from "../lib/host-exec.js";

const inputSchema = z.object({
  feature: z.string().min(1),
});

// spawn.py status <feature> - argv byte-for-byte per RFC S6.
export function buildArgv(input: z.infer<typeof inputSchema>): string[] {
  return ["status", input.feature];
}

export default defineTool({
  description:
    "Report a mission's fleet status (spawn.py status <feature>): container/VM liveness, the orbal-net server, the eve connector (if any), and live agents.",
  inputSchema,
  async execute(input) {
    return hostExec(python3Bin(), [spawnPyPath(), ...buildArgv(input)]);
  },
});
