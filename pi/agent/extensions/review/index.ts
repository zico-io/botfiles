/**
 * Pi Review Extension
 *
 * Opens markdown and diff files for review in a herdr pane.
 * Uses glow for markdown and hunk for diffs/patches.
 *
 * Tools provided:
 *   - review  Open a file in a side pane with glow/hunk
 *
 * Usage:
 *   pi -e .pi/agent/extensions/review
 *
 * Prerequisites:
 *   - Running inside herdr (HERDR_ENV=1)
 *   - glow and hunk installed
 */

import path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// ─── Types ────────────────────────────────────────────────────

interface ExecResult {
	stdout: string;
	stderr: string;
	code: number;
}

// ─── Helpers ──────────────────────────────────────────────────

function isInsideHerdr(): boolean {
	return process.env.HERDR_ENV === "1";
}

function guestToHostPath(guestPath: string): string {
	const gvm = process.env.GONDOLIN_VM;
	const hostCwd = process.env.GONDOLIN_HOST_CWD;
	if (
		gvm === "1" &&
		hostCwd &&
		(guestPath === "/workspace" || guestPath.startsWith("/workspace/"))
	) {
		return path.join(hostCwd, guestPath.slice("/workspace".length));
	}
	return guestPath;
}

async function herdrExec(
	pi: ExtensionAPI,
	args: string[],
): Promise<ExecResult> {
	return pi.exec("herdr", args) as unknown as ExecResult;
}

async function herdrExecJson<T>(pi: ExtensionAPI, args: string[]): Promise<T> {
	const result = await herdrExec(pi, args);
	if (result.code !== 0) {
		throw new Error(`herdr ${args.join(" ")} failed: ${result.stderr}`);
	}
	try {
		return JSON.parse(result.stdout) as T;
	} catch {
		throw new Error(`herdr ${args.join(" ")}: invalid JSON response`);
	}
}

interface PaneInfo {
	pane_id: string;
	focused: boolean;
}

async function focusedPane(pi: ExtensionAPI): Promise<string> {
	const data = await herdrExecJson<{ result: { panes: PaneInfo[] } }>(pi, [
		"pane",
		"list",
	]);
	const focused = data.result.panes.find((p) => p.focused);
	if (!focused) throw new Error("No focused pane found");
	return focused.pane_id;
}

async function splitPane(
	pi: ExtensionAPI,
	parent: string,
	direction: "right" | "down",
): Promise<string> {
	const data = await herdrExecJson<{ result: { pane: { pane_id: string } } }>(
		pi,
		["pane", "split", parent, "--direction", direction, "--no-focus"],
	);
	return data.result.pane.pane_id;
}

async function renamePane(
	pi: ExtensionAPI,
	paneId: string,
	label: string,
): Promise<void> {
	await herdrExec(pi, ["pane", "rename", paneId, label]);
}

async function runInPane(
	pi: ExtensionAPI,
	paneId: string,
	command: string,
): Promise<void> {
	await herdrExec(pi, ["pane", "run", paneId, command]);
}

// ─── Review tool ──────────────────────────────────────────────

interface ReviewParams {
	kind: "md" | "diff" | "patch";
	files: string[];
}

export default function (pi: ExtensionAPI) {
	pi.registerTool({
		name: "review",
		label: "Open in Review Pane",
		description:
			"Open a markdown or diff file for review in a side herdr pane. Uses glow for markdown, hunk for diffs/patches.",
		parameters: {
			type: "object",
			properties: {
				kind: {
					type: "string",
					enum: ["md", "diff", "patch"],
					description:
						"md: open a markdown file with glow. diff: compare two files with hunk diff. patch: review a patch file with hunk patch.",
				},
				files: {
					type: "array",
					items: { type: "string" },
					description:
						"File paths. md and patch take one file. diff takes two files (left, right).",
				},
			},
			required: ["kind", "files"],
		},
		async execute(
			_id: string,
			params: ReviewParams,
			_signal: AbortSignal,
			_onUpdate: ((update: unknown) => void) | undefined,
			_ctx: { cwd: string; hasUI?: boolean; [key: string]: unknown },
		) {
			if (!isInsideHerdr()) {
				return {
					content: [
						{
							type: "text" as const,
							text: "Error: not running inside herdr (HERDR_ENV != 1).",
						},
					],
				};
			}

			const { kind, files } = params;
			const hostFiles = files.map(guestToHostPath);

			try {
				let label: string;
				let cmd: string;

				switch (kind) {
					case "md": {
						if (files.length < 1)
							throw new Error("md review requires one file path");
						const file = hostFiles[0];
						label = "md-review";
						cmd = `glow -t '${file}'`;
						break;
					}
					case "diff": {
						if (files.length < 2)
							throw new Error(
								"diff review requires two file paths (left, right)",
							);
						const [a, b] = hostFiles;
						label = "diff-review";
						cmd = `hunk diff '${a}' '${b}'`;
						break;
					}
					case "patch": {
						if (files.length < 1)
							throw new Error("patch review requires one file path");
						const file = hostFiles[0];
						label = "patch-review";
						cmd = `hunk patch '${file}'`;
						break;
					}
					default:
						throw new Error(`Unknown review kind: ${kind}`);
				}

				const parent = await focusedPane(pi);
				const newPane = await splitPane(pi, parent, "right");
				await renamePane(pi, newPane, label);
				await runInPane(pi, newPane, cmd);

				return {
					content: [
						{
							type: "text" as const,
							text: `Opened ${kind} review in pane ${newPane}: ${cmd}`,
						},
					],
				};
			} catch (err) {
				const msg = err instanceof Error ? err.message : String(err);
				return {
					content: [{ type: "text" as const, text: `Review error: ${msg}` }],
				};
			}
		},
	});
}
