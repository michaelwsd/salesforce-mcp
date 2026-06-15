# Salesforce MCP Server

A remote MCP (Model Context Protocol) server that gives Claude full CRUD access to the Armitage Salesforce org. Built with FastMCP and deployed on Render.

## Architecture

```
Claude Desktop / Claude Code
        |
        v  (Streamable HTTP)
  Salesforce MCP Server
  FastMCP + Python
  Hosted on Render
        |
        v  (REST API)
  Armitage Salesforce Org
```

## Tools (24)

### Core CRUD
| Tool | Description |
|------|-------------|
| `query` | Run arbitrary SOQL queries |
| `search` | Run SOSL full-text search across objects |
| `get_record` | Get a single record by type and ID |
| `create_record` | Create a new record |
| `update_record` | Update an existing record |
| `delete_record` | Delete a record |

### Discovery & Metadata
| Tool | Description |
|------|-------------|
| `list_objects` | List all queryable SObjects in the org |
| `describe_object` | Get field metadata for an object |
| `describe_field` | Get picklist values, type, constraints for a field |

### Notes & Activities
| Tool | Description |
|------|-------------|
| `get_notes` | Get all notes for a record — searches Event Descriptions (APC/NL/HM notes), Task Descriptions, classic Notes, and ContentNotes. Supports `since` date filter and `limit`. |
| `get_activities` | Get all Tasks and Events for a record with full Description content |
| `get_feed` | Get Chatter feed posts on a record |
| `get_field_history` | Get change history (who changed what, when) |

### Company Deep-Dive
| Tool | Description |
|------|-------------|
| `get_company_overview` | Pull everything for an Opportunity — record fields (human-readable names), Account, Contacts, Tasks, Events, Notes, Files, Growth Summaries |
| `get_opportunity_field_map` | Get the mapping of legacy `fid` field names to readable labels (e.g. `fid15__c` -> "EBITDA estimate ($M)") |
| `get_related_contacts` | Get contacts via OpportunityContactRole or Account |

### Files
| Tool | Description |
|------|-------------|
| `list_files` | List ContentDocuments linked to a record |
| `get_file` | Get file metadata and download URL |
| `attach_file_link` | Link an external URL to a record as a ContentVersion |

### Reports & Dashboards
| Tool | Description |
|------|-------------|
| `list_reports` | List all reports |
| `run_report` | Execute a report by ID |
| `list_dashboards` | List all dashboards |

### Bulk Operations
| Tool | Description |
|------|-------------|
| `bulk_upsert` | Upsert multiple records via Bulk API |
| `bulk_query` | Async query for large datasets |

## Setup for Team Members

Add this to your `claude_desktop_config.json` and restart Claude Desktop:

```json
{
  "mcpServers": {
    "armitage-salesforce": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://salesforce-mcp-cq58.onrender.com/mcp",
        "--header",
        "Authorization:${AUTH_TOKEN}"
      ],
      "env": {
        "AUTH_TOKEN": "Bearer <your-api-key>"
      }
    }
  }
}
```

Config file location:
- **Mac:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Requires Node.js 18+ (for `npx`).

## Local Development

```bash
# Clone and install
git clone git@github.com:michaelwsd/salesforce-mcp.git
cd salesforce-mcp
uv sync

# Create .env with credentials
cp .env.example .env  # then fill in values

# Run locally
python main.py
```

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `SALESFORCE_DOMAIN` | Salesforce instance URL |
| `SALESFORCE_USERNAME` | Login email |
| `SALESFORCE_PASSWORD` | Password |
| `SALESFORCE_SECURITY_TOKEN` | Security token |
| `CONSUMER_KEY` | Connected App consumer key |
| `CONSUMER_SECRET` | Connected App consumer secret |
| `MCP_API_KEYS` | Comma-separated valid API keys |
| `PORT` | Server port (default 8080) |

## Deployment

Hosted on Render (free tier). Auto-deploys on push to `main`.

The Dockerfile builds a Python 3.12 image and runs `python main.py`, which starts a uvicorn server with Streamable HTTP transport on the port specified by the `PORT` env var.

## Tech Stack

- **FastMCP** — MCP server framework
- **simple-salesforce** — Salesforce REST API client
- **uvicorn** — ASGI server
- **Starlette** — API key auth middleware
- **Render** — hosting (free tier)
