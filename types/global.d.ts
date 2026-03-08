// Minimal ambient type shims to satisfy TypeScript in local dev/editor.
// Runtime types are provided by the host (OpenClaw) and installed packages.

declare module "openclaw/plugin-sdk" {
  // Loosely typed API surface sufficient for this plugin's usage.
  export interface OpenClawPluginApi {
    pluginConfig: unknown;
    resolvePath(path: string): string;
    logger: {
      debug?: (...args: any[]) => void;
      info: (...args: any[]) => void;
      warn: (...args: any[]) => void;
      error?: (...args: any[]) => void;
    };
    config?: any;

    registerCli: (...args: any[]) => void;
    registerHook: (...args: any[]) => void;
    registerService: (...args: any[]) => void;

    on: (event: string, handler: (...args: any[]) => any) => void;
  }
}

declare module "@xenova/transformers" {
  export const pipeline: any;
  export const env: any;
}
