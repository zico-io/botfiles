/**
 * Pi Review Extension
 *
 * `review` tool: opens a markdown or diff/patch file in a side herdr pane through
 * scripts/review-pane (glow for markdown, delta for diffs).
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { Type } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

function guestToHostPath(guestPath: string): string {
	const hostCwd = process.env.GONDOLIN_HOST_CWD;
	if (
		process.env.GONDOLIN_VM === "1" &&
		hostCwd &&
		(guestPath === "/workspace" || guestPath.startsWith("/workspace/"))
	) {
		return path.join(hostCwd, guestPath.slice("/workspace".length));
	}
	return guestPath;
}

export default function (pi: ExtensionAPI) {
	pi.registerTool({
		name: "review",
		label: "Open in Review Pane",
		description:
			"Open a markdown (.md) or diff (.diff/.patch) file for the user to review in a side herdr pane.",
		parameters: Type.Object({
			path: Type.String({ description: "Markdown or diff/patch file to show" }),
		}),
		async execute(_id, params) {
			// ~/.pi/agent/extensions is a symlink into the repo; scripts/ sits at its root.
			const extensions = fs.realpathSync(path.join(os.homedir(), ".pi", "agent", "extensions"));
			const reviewPane = path.join(extensions, "..", "..", "..", "scripts", "review-pane");
			const file = guestToHostPath(params.path);
			const { stdout, stderr, code } = await pi.exec(reviewPane, [file]);
			const text =
				code === 0
					? stdout.trim() || `Opened ${file} in a review pane.`
					: `Review error: ${stderr || stdout}`;
			return { content: [{ type: "text", text }] };
		},
	});
}
