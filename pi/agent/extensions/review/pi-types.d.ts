/**
 * Minimal type declarations for Pi extension development.
 *
 * The Pi runtime provides these at execution time. This file exists
 * only for TypeScript checking during development — it is never
 * loaded at runtime.
 */

// pony tail: global process type for pi runtime (no @types/node needed)
declare const process: { env: Record<string, string | undefined> };

declare module "@earendil-works/pi-coding-agent" {
  export interface ExtensionAPI {
    exec(
      command: string,
      args: string[],
    ): Promise<{ stdout: string; stderr: string; code: number }>;
    registerTool(tool: {
      name: string;
      label: string;
      description: string;
      parameters: Record<string, unknown>;
      execute(
        id: string,
        params: any,
        signal: AbortSignal,
        onUpdate: ((update: any) => void) | undefined,
        ctx: { cwd: string; hasUI?: boolean; [key: string]: any },
      ): Promise<{
        content: Array<{ type: string; text: string }>;
        details?: any;
      }>;
    }): void;
    on(event: string, handler: (event: any, ctx?: any) => any): void;
  }
}
