import { defineTool } from "eve/tools";
import { z } from "zod";
import { hostExec, planPanePyPath, python3Bin } from "../lib/host-exec.js";

const inputSchema = z.object({
  file: z.string().min(1).describe("Path to the file to open in the live plan pane"),
});

// plan_pane.py open <file> - argv byte-for-byte per RFC S7.1.
export function buildArgv(input: z.infer<typeof inputSchema>): string[] {
  return ["open", input.file];
}

export default defineTool({
  description:
    "Open a file in a live plan-pane split next to the human (plan_pane.py open <file>) - the shared-editor loop /scope-mission drives interactively. Herdr-specific, no eve channel analog, so it stays a wrapped CLI tool (RFC S7.1).",
  inputSchema,
  async execute(input) {
    return hostExec(python3Bin(), [planPanePyPath(), ...buildArgv(input)]);
  },
});
