import { defineTool } from "eve/tools";
import { z } from "zod";
import { hostExec, planPanePyPath, python3Bin } from "../lib/host-exec.js";

const inputSchema = z.object({});

// plan_pane.py selection - argv byte-for-byte per RFC S7.1 (no arguments).
export function buildArgv(_input: z.infer<typeof inputSchema>): string[] {
  return ["selection"];
}

export default defineTool({
  description:
    "Read the human's current selection/cursor in the open plan pane (plan_pane.py selection), so the model can pick up where the human's edit left off.",
  inputSchema,
  async execute(input) {
    return hostExec(python3Bin(), [planPanePyPath(), ...buildArgv(input)]);
  },
});
