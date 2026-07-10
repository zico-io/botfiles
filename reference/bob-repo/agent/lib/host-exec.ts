// Shared host shell-out for the orchestration tools (RFC S6). Unlike
// lib/orbal-net.ts (native fetch, works deployed), these tools run only in a
// LOCAL bob (RFC thesis bet 2: L1 has the host shell, spawn.py/herdr/gh are
// on PATH) - so shelling out here is correct, not a workaround.
//
// spawn.py and plan_pane.py live in host .botfiles/orchestration, not in this
// repo (non-goal: do not copy/modify them here) - resolve their path from
// ORCHESTRATION_DIR with a sensible default rather than hardcoding one path.

import { spawn } from "node:child_process";

export interface HostExecResult {
  readonly stdout: string;
  readonly stderr: string;
  readonly exitCode: number;
}

// A non-zero exit becomes this - a normal thrown Error the eve tool runtime
// turns into a failed tool call the model sees, not an uncaught crash
// (RFC S6: "errors surface as tool failures, not crashes").
export class HostExecError extends Error {
  readonly argv: readonly string[];
  readonly stdout: string;
  readonly stderr: string;
  readonly exitCode: number;

  constructor(argv: readonly string[], result: HostExecResult) {
    super(
      `${argv.join(" ")} exited ${result.exitCode}${
        result.stderr.trim() ? `: ${result.stderr.trim()}` : ""
      }`,
    );
    this.name = "HostExecError";
    this.argv = argv;
    this.stdout = result.stdout;
    this.stderr = result.stderr;
    this.exitCode = result.exitCode;
  }
}

export function hostExec(command: string, args: readonly string[]): Promise<HostExecResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk: Buffer) => (stdout += chunk));
    child.stderr.on("data", (chunk: Buffer) => (stderr += chunk));
    child.on("error", reject);
    child.on("close", (code) => {
      const result: HostExecResult = { stdout, stderr, exitCode: code ?? -1 };
      if (result.exitCode !== 0) {
        reject(new HostExecError([command, ...args], result));
      } else {
        resolve(result);
      }
    });
  });
}

export function orchestrationDir(): string {
  return process.env.ORCHESTRATION_DIR ?? "/opt/botfiles/orchestration";
}

export function spawnPyPath(): string {
  return `${orchestrationDir()}/spawn.py`;
}

export function planPanePyPath(): string {
  return `${orchestrationDir()}/plan_pane.py`;
}

export function python3Bin(): string {
  return process.env.PYTHON3 ?? "python3";
}

export function herdrBin(): string {
  return process.env.HERDR_BIN ?? "herdr";
}
