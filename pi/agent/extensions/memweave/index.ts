/**
 * memweave — Persistent agent memory via Markdown files + SQLite FTS5.
 *
 * Inspired by memweave (github.com/sachinsharma9780/memweave).
 * Uses Python stdlib only — no numpy, no embeddings, no external services.
 *
 * Tools provided: mem_search, mem_write, mem_list, mem_stats, mem_rebuild
 */

import { spawn } from "node:child_process";
import path from "node:path";
import { Type } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const WORKSPACE = process.cwd();
const MEM_SCRIPT = path.resolve(WORKSPACE, "scripts/mem.py");

// ponytail: try python3.12 then python3; execSync("which") resolves paths that don't survive into spawn

async function spawnMem(
	args: string[],
): Promise<{ stdout: string; stderr: string; exitCode: number }> {
	// ponytail: try python3.12 then python3 — which(1) paths don't survive the spawn namespace
	for (const bin of ["python3.12", "python3"]) {
		try {
			return await new Promise((resolve, reject) => {
				const proc = spawn(bin, [MEM_SCRIPT, ...args], {
					cwd: WORKSPACE,
					env: { ...process.env, PYTHONUNBUFFERED: "1" },
				});
				let stdout = "";
				let stderr = "";
				proc.stdout.on("data", (d: Buffer) => (stdout += d.toString()));
				proc.stderr.on("data", (d: Buffer) => (stderr += d.toString()));
				proc.on("error", (err) => reject(err));
				proc.on("close", (code: number | null) => {
					resolve({ stdout, stderr, exitCode: code ?? 1 });
				});
			});
		} catch {
			// try next binary
		}
	}
	throw new Error("no python binary found");
}

function runMem(args: string[]) {
	return spawnMem(args);
}

export default function (pi: ExtensionAPI) {
	// ── orchestration safety net ──
	let orchestrationUsed = false;
	let memWriteCalled = false;

	// tool_call the orchestration tools: subagent, fleet_boot, orchestrate_*
	const orchestrationTools = new Set([
		"subagent",
		"fleet_boot",
		"orchestrate_fan_out",
		"orchestrate_race",
		"orchestrate_pipeline",
	]);

	pi.on("tool_call", async (event) => {
		if (orchestrationTools.has(event.toolName)) orchestrationUsed = true;
		if (event.toolName === "mem_write") memWriteCalled = true;
	});

	pi.on("agent_end", async () => {
		if (orchestrationUsed && !memWriteCalled) {
			pi.sendUserMessage(
				"Mission complete — synthesize memories from this session. Review the mission context, call mem_search for related existing memories, then call mem_write to create/update memories. Be concise.",
				{ deliverAs: "followUp" },
			);
		}
	});

	// ── mem_search ──
	pi.registerTool({
		name: "mem_search",
		description:
			"Search agent memory (Markdown files indexed by SQLite FTS5). Returns ranked snippets with file:line references. Use for recalling user preferences, past decisions, or project context.",
		parameters: Type.Object({
			query: Type.String({
				description: "Search query (supports multi-word AND/OR matching)",
			}),
		}),
		async execute(_toolCallId, params) {
			const { stdout, stderr } = await runMem(["search", params.query]);
			if (stderr) console.error("[mem_search]", stderr);
			return { content: [{ type: "text", text: stdout || "(no results)" }] };
		},
	});

	// ── mem_write ──
	pi.registerTool({
		name: "mem_write",
		description:
			"Write a new memory file and index it. Use when you discover facts worth remembering across sessions (user preferences, decisions, project conventions). Files are plain Markdown — inspect them in pi/memory/.",
		parameters: Type.Object({
			name: Type.String({
				description:
					"Short slug for the memory file (e.g. 'preferences', 'api-keys')",
			}),
			content: Type.String({ description: "Markdown content to store" }),
		}),
		async execute(_toolCallId, params) {
			const { stdout, stderr } = await runMem([
				"write",
				params.name,
				params.content,
			]);
			if (stderr) console.error("[mem_write]", stderr);
			return { content: [{ type: "text", text: stdout || "done" }] };
		},
	});

	// ── mem_list ──
	pi.registerTool({
		name: "mem_list",
		description:
			"List all indexed memory files with chunk counts and timestamps.",
		parameters: Type.Object({}),
		async execute() {
			const { stdout } = await runMem(["list"]);
			return {
				content: [{ type: "text", text: stdout || "(no indexed files)" }],
			};
		},
	});

	// ── mem_stats ──
	pi.registerTool({
		name: "mem_stats",
		description:
			"Show memory system statistics: file count, chunk count, DB size.",
		parameters: Type.Object({}),
		async execute() {
			const { stdout } = await runMem(["stats"]);
			return { content: [{ type: "text", text: stdout }] };
		},
	});

	// ── mem_rebuild ──
	pi.registerTool({
		name: "mem_rebuild",
		description:
			"Rebuild the search index from all Markdown files in the memory directory.",
		parameters: Type.Object({}),
		async execute() {
			const { stdout } = await runMem(["rebuild"]);
			return { content: [{ type: "text", text: stdout || "done" }] };
		},
	});
}
