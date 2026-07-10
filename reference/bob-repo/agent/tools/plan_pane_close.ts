import { defineTool } from "eve/tools";
import { z } from "zod";
import { hostExec, planPanePyPath, python3Bin } from "../lib/host-exec.js";

const inputSchema = z.object({
  paneId: z.string().min(1).describe("Pane id returned by plan_pane_open"),
});

// plan_pane.py close <pane-id> - argv byte-for-byte per RFC S7.1.
export function buildArgv(input: z.infer<typeof inputSchema>): string[] {
  return ["close", input.paneId];
}

export default defineTool({
  description: "Close a plan pane opened by plan_pane_open (plan_pane.py close <pane-id>).",
  inputSchema,
  async execute(input) {
    return hostExec(python3Bin(), [planPanePyPath(), ...buildArgv(input)]);
  },
});
