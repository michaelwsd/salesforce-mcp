// Bundles src/index.js and its dependencies into one file and packs it with
// manifest.json into dist/armitage-salesforce.mcpb. A single bundled file means
// installing the extension unpacks no node_modules tree on the user's machine.

import { execFileSync } from "node:child_process";
import { cpSync, mkdirSync, rmSync } from "node:fs";
import { build } from "esbuild";

const stage = "dist/bundle";
rmSync("dist", { recursive: true, force: true });
mkdirSync(stage, { recursive: true });

await build({
  entryPoints: ["src/index.js"],
  outfile: `${stage}/server/index.js`,
  bundle: true,
  platform: "node",
  target: "node18",
  format: "esm",
  legalComments: "none",
  // ESM bundles of CommonJS dependencies still call require() for Node builtins.
  banner: { js: "import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);" },
});
// Node only treats .js as ESM next to a package.json that says so.
cpSync("bundle-package.json", `${stage}/package.json`);
cpSync("manifest.json", `${stage}/manifest.json`);

// Call the CLI through node rather than npx so Windows needs no shell quoting.
const mcpb = (...args) =>
  execFileSync(process.execPath, ["node_modules/@anthropic-ai/mcpb/dist/cli/cli.js", ...args], { stdio: "inherit" });
mcpb("validate", `${stage}/manifest.json`);
mcpb("pack", stage, "dist/armitage-salesforce.mcpb");
