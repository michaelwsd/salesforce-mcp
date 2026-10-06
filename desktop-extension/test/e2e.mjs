// End-to-end test of the packed extension, run the way Claude Desktop runs it:
// unpack dist/armitage-salesforce.mcpb, start server/index.js with node over
// stdio, and talk MCP to it.
//
// By default it starts the Python server from the repo root on a free port with
// a throwaway API key. Set MCP_TEST_SERVER_URL and MCP_TEST_API_KEY to test
// against a running server (e.g. production) instead.

import assert from "node:assert/strict";
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const extensionDir = fileURLToPath(new URL("..", import.meta.url));
const repoRoot = join(extensionDir, "..");
const isWindows = process.platform === "win32";

async function freePort() {
  return new Promise((resolve) => {
    const srv = createServer().listen(0, "127.0.0.1", () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

async function startLocalServer() {
  const port = await freePort();
  const key = "e2e-test-key";
  const proc = spawn("uv", ["run", "--frozen", "python", "main.py"], {
    cwd: repoRoot,
    env: { ...process.env, PORT: String(port), MCP_API_KEYS: key },
    stdio: ["ignore", "inherit", "inherit"],
  });
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 240; i++) {
    try {
      if ((await fetch(`${base}/api/uptime`)).ok) return { url: `${base}/mcp`, key, stop: () => killTree(proc) };
    } catch {}
    await new Promise((r) => setTimeout(r, 500));
  }
  killTree(proc);
  throw new Error("Local server did not start");
}

function killTree(proc) {
  if (isWindows) spawnSync("taskkill", ["/pid", String(proc.pid), "/t", "/f"]);
  else proc.kill();
}

function unpack() {
  const dir = mkdtempSync(join(tmpdir(), "armitage-mcpb-"));
  const cli = join(extensionDir, "node_modules", "@anthropic-ai", "mcpb", "dist", "cli", "cli.js");
  execFileSync(process.execPath, [cli, "unpack", join(extensionDir, "dist", "armitage-salesforce.mcpb"), dir], {
    stdio: "ignore",
  });
  return dir;
}

async function connect(dir, url, key) {
  const client = new Client({ name: "e2e", version: "1.0.0" });
  const transport = new StdioClientTransport({
    // process.execPath stands in for Claude Desktop's built-in node.
    command: process.execPath,
    args: [join(dir, "server", "index.js")],
    env: { ...process.env, MCP_SERVER_URL: url, MCP_API_KEY: key },
    stderr: "pipe",
  });
  await client.connect(transport, { timeout: 120_000 });
  return client;
}

const results = [];
async function test(name, fn) {
  try {
    await fn();
    results.push(true);
    console.log(`ok   ${name}`);
  } catch (error) {
    results.push(false);
    console.log(`FAIL ${name}\n     ${error.stack || error}`);
  }
}

const server = process.env.MCP_TEST_SERVER_URL
  ? { url: process.env.MCP_TEST_SERVER_URL, key: process.env.MCP_TEST_API_KEY, stop() {} }
  : await startLocalServer();
const dir = unpack();

try {
  await test("lists tools and prompts, calls a tool", async () => {
    const client = await connect(dir, server.url, server.key);
    const { tools } = await client.listTools();
    assert.ok(tools.length >= 30, `expected the full tool list, got ${tools.length}`);
    assert.ok(tools.some((t) => t.name === "query"));
    const { prompts } = await client.listPrompts();
    assert.ok(prompts.some((p) => p.name === "screen"));
    const result = await client.callTool({ name: "get_opportunity_field_map", arguments: {} });
    assert.ok(!result.isError);
    assert.match(JSON.stringify(result.content), /fid14__c/);
    await client.close();
  });

  await test("accepts a key pasted with its Bearer prefix", async () => {
    const client = await connect(dir, server.url, `  Bearer ${server.key} `);
    assert.ok((await client.listTools()).tools.length > 0);
    await client.close();
  });

  // Claude Desktop starts the same server several times at once (chat plus the
  // Cowork/Code pool); that is what corrupted the npx cache on Windows.
  await test("several instances start at the same time", async () => {
    const clients = await Promise.all([1, 2, 3, 4].map(() => connect(dir, server.url, server.key)));
    const counts = await Promise.all(clients.map(async (c) => (await c.listTools()).tools.length));
    assert.ok(counts.every((n) => n === counts[0] && n > 0), `tool counts differ: ${counts}`);
    await Promise.all(clients.map((c) => c.close()));
  });

  await test("a wrong key gives a clear error instead of a crash", async () => {
    await assert.rejects(connect(dir, server.url, "wrong-key"), /API key was rejected/);
  });

  await test("an unreachable server gives a clear error instead of a crash", async () => {
    await assert.rejects(connect(dir, `http://127.0.0.1:${await freePort()}/mcp`, server.key), /Could not reach/);
  });
} finally {
  server.stop();
  rmSync(dir, { recursive: true, force: true });
}

const failed = results.filter((ok) => !ok).length;
console.log(`\n${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
