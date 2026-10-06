// Stdio <-> Streamable HTTP bridge for the Armitage Salesforce MCP server.
//
// Claude Desktop runs this with its built-in Node, so installing the extension
// needs no npm, npx or PATH setup on the user's machine. Messages are forwarded
// unchanged; the server is stateless, so there is no session to keep alive and
// a Render restart or sleep is invisible to the client.

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { StreamableHTTPClientTransport, StreamableHTTPError } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

const DEFAULT_URL = "https://salesforce-mcp-cq58.onrender.com/mcp";

const serverUrl = new URL(process.env.MCP_SERVER_URL || DEFAULT_URL);
// Accept the key with or without a "Bearer " prefix, since people paste both.
const apiKey = (process.env.MCP_API_KEY || "").trim().replace(/^Bearer\s+/i, "");

const log = (...args) => console.error("[armitage-salesforce]", ...args);

if (!apiKey) {
  log("No API key configured. Set it in Claude Desktop > Settings > Extensions > Armitage Salesforce.");
}

const local = new StdioServerTransport();
const remote = new StreamableHTTPClientTransport(serverUrl, {
  requestInit: { headers: { Authorization: `Bearer ${apiKey}` } },
});

// Requests we have forwarded, so an initialize response can be recognised and
// its negotiated protocol version passed on to later HTTP requests.
const pendingInitialize = new Set();

function describeFailure(error) {
  if (error instanceof StreamableHTTPError) {
    if (error.code === 401) {
      return "The Armitage Salesforce API key was rejected. Check it in Claude Desktop > Settings > Extensions > Armitage Salesforce.";
    }
    return `The Armitage Salesforce server returned HTTP ${error.code}: ${error.message}`;
  }
  return `Could not reach the Armitage Salesforce server at ${serverUrl.origin} (${error?.cause?.code || error?.message || error}). Check your internet connection and try again.`;
}

local.onmessage = async (message) => {
  if (message.method === "initialize" && message.id !== undefined) {
    pendingInitialize.add(message.id);
  }
  try {
    await remote.send(message);
  } catch (error) {
    // The transport has already logged the error through remote.onerror.
    // Answer requests with an error instead of leaving Claude waiting on them;
    // notifications have no id and need no answer.
    if (message.method !== undefined && message.id !== undefined) {
      pendingInitialize.delete(message.id);
      await local.send({
        jsonrpc: "2.0",
        id: message.id,
        error: { code: -32000, message: describeFailure(error) },
      });
    }
  }
};

remote.onmessage = async (message) => {
  if (message.id !== undefined && pendingInitialize.delete(message.id) && message.result?.protocolVersion) {
    remote.setProtocolVersion(message.result.protocolVersion);
  }
  await local.send(message);
};

remote.onerror = (error) => log("Server connection error:", error);
local.onerror = (error) => log("Client connection error:", error);

local.onclose = async () => {
  await remote.close();
  process.exit(0);
};

await remote.start();
await local.start();
log(`Forwarding to ${serverUrl.href}`);
