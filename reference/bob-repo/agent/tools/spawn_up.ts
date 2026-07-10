import { readFileSync } from "node:fs";
import { dirname, isAbsolute, resolve } from "node:path";
import { defineTool } from "eve/tools";
import { z } from "zod";
import { attachRoom } from "../lib/connector-control.js";
import { hostExec, orchestrationDir, python3Bin, spawnPyPath } from "../lib/host-exec.js";

const inputSchema = z.object({
  rosterPath: z
    .string()
    .min(1)
    .describe("Path to the roster JSON, e.g. orchestration/<feature>.roster.json"),
  teams: z
    .array(z.string().min(1))
    .optional()
    .describe("Lead roles to spawn (AGENTS.md: 'pass lead roles to up, or omit for all')"),
});

// spawn.py up <roster.json> [teams] - argv byte-for-byte against the real
// CLI dispatch (`up(args[1], args[2] if len(args) == 3 else None)`; `only`
// is select_leads()'s single comma-list positional, not a variadic list -
// verified against git show 9d4db12:reference/botfiles-current/orchestration/spawn.py).
// Pure - kept byte-for-byte on the raw input.rosterPath (see spawn-tools-argv.test.ts);
// path resolution for the live subprocess happens in execute() via resolveRosterPath.
export function buildArgv(input: z.infer<typeof inputSchema>): string[] {
  const args = ["up", input.rosterPath];
  if (input.teams && input.teams.length > 0) args.push(input.teams.join(","));
  return args;
}

// hostExec spawns spawn.py inheriting eve's cwd (the bob repo), not .botfiles -
// so a relative rosterPath like "orchestration/<feat>.roster.json" (AGENTS.md's
// own convention: `orchestration/roster.example.json`, named relative to
// .botfiles) FileNotFounds against the wrong root. Absolutize before use: an
// absolute path passes through, a relative one resolves against
// ORCHESTRATION_DIR's parent (.botfiles, where spawn.py and its roster live).
export function resolveRosterPath(rosterPath: string): string {
  return isAbsolute(rosterPath) ? rosterPath : resolve(dirname(orchestrationDir()), rosterPath);
}

export default defineTool({
  description:
    "Stand up a mission fleet from a roster (spawn.py up <roster.json> [teams]). Starts the mission's orbal-net server and creates mission-<feature>; spawns only the given lead roles, or every team in the roster if omitted. Also attaches bob's connector to the new mission-<feature> room (RFC S8) so bob starts receiving that mission's reports.",
  inputSchema,
  async execute(input) {
    const resolvedRosterPath = resolveRosterPath(input.rosterPath);
    const result = await hostExec(python3Bin(), [
      spawnPyPath(),
      ...buildArgv({ ...input, rosterPath: resolvedRosterPath }),
    ]);
    // The fleet is already live at this point - a roster read or an attach
    // failure must not read as "up failed" (RFC S8: adding one mission's
    // subscription must not disturb any other). Read the same roster file
    // spawn.py just consumed (additive local read, no argv change) to learn
    // its feature slug, since spawn_up's own input never carries it.
    const feature = (JSON.parse(readFileSync(resolvedRosterPath, "utf8")) as { feature: string }).feature;
    const room = `mission-${feature}`;
    try {
      await attachRoom(room);
      return { up: result.stdout, attached: true, room };
    } catch (err) {
      return {
        up: result.stdout,
        attached: false,
        room,
        warning: `fleet is up but connector attach failed; retry - bob will not receive this mission's reports (${err instanceof Error ? err.message : String(err)})`,
      };
    }
  },
});
