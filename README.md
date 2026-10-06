# Salesforce MCP Server

A remote MCP (Model Context Protocol) server that gives Claude full CRUD access to the Armitage Salesforce org and GOWT Excel data on OneDrive. Built with FastMCP and deployed on Render.

## Architecture

```
Claude Desktop / Claude Code
        |
        v  (Streamable HTTP)
  Salesforce MCP Server
  FastMCP + Python
  Hosted on Render
        |
        +--> Armitage Salesforce Org (REST API)
        +--> OneDrive / GOWT Data Scrape (Microsoft Graph API)
```

**Status page:** https://salesforce-mcp-cq58.onrender.com/

## Project Structure

```
salesforce-mcp/
├── main.py              # Entry point — starts uvicorn, adds auth + status route
├── Dockerfile
├── pyproject.toml
├── app/
│   ├── __init__.py      # FastMCP instance + logging
│   ├── client.py        # Salesforce OAuth2 connection
│   ├── activities.py    # Archived-aware Task/Event/EmailMessage lookups
│   ├── auth.py          # API key middleware (Bearer token)
│   ├── field_map.py     # Legacy fid field name mappings
│   ├── status.py        # Status page + uptime API
│   ├── tools/
│   │   ├── __init__.py  # Imports all tool modules
│   │   ├── crud.py      # query, query_more, search, get/create/update/delete_record
│   │   ├── metadata.py  # list_objects, describe_object, describe_field
│   │   ├── files.py     # list_files, get_file, download_file, attach_file_link
│   │   ├── reports.py   # list_reports, run_report, list_dashboards
│   │   ├── notes.py     # get_notes, get_activities, get_emails, get_feed, get_field_history
│   │   ├── company.py   # get_company_overview, get_opportunity_field_map, get_related_contacts, get_gowt_opportunities
│   │   ├── bulk.py      # bulk_upsert, bulk_query
│   │   ├── onedrive.py  # list_onedrive_files, download_onedrive_file, read_gowt_excel
│   │   ├── outreach.py  # upload_email_attachment, bulk_email
│   │   └── screener.py  # get_screener_guide, create_deal, build_screener, approve_screener
│   └── screener/        # Screener builder + drafts: build.py, drafts.py, fix_xml.py, guide.md, example_spec.json
```

## Tools (37)

### Core CRUD
| Tool | Description |
|------|-------------|
| `query` | Run arbitrary SOQL queries (pages of 2000; `include_archived=True` for archived Tasks/Events and deleted rows) |
| `query_more` | Fetch the next batch of a large `query` result |
| `search` | Run SOSL full-text search across objects |
| `get_record` | Get a single record by type and ID |
| `create_record` | Create a new record |
| `update_record` | Update an existing record |
| `delete_record` | Delete a record |

### Discovery & Metadata
| Tool | Description |
|------|-------------|
| `list_objects` | List all queryable SObjects in the org |
| `describe_object` | Get field metadata, lookup targets, and child relationships for an object |
| `describe_field` | Get picklist values, type, constraints for a field |

### Notes & Activities
| Tool | Description |
|------|-------------|
| `get_notes` | Get all notes for a record — searches Event Descriptions (APC/NL/HM notes), Task Descriptions, classic Notes, and ContentNotes. Supports `since` date filter and `limit`. |
| `get_activities` | Get all Tasks and Events for a record with full Description content |
| `get_emails` | Get EmailMessages for a record (Related To for deals/accounts; sender or recipient for people) |
| `get_feed` | Get Chatter feed posts (with comments) on a record |
| `get_field_history` | Get change history (who changed what, when) |

### Company Deep-Dive
| Tool | Description |
|------|-------------|
| `get_company_overview` | Pull everything for an Opportunity — record fields (human-readable names), Account, Contacts, Tasks, Events, Notes, Files, Growth Summaries |
| `get_opportunity_field_map` | Get the mapping of legacy `fid` field names to readable labels (e.g. `fid15__c` → "EBITDA estimate ($M)") |
| `get_related_contacts` | Get contacts via OpportunityContactRole or Account |
| `get_gowt_opportunities` | Get GOWT pipeline deals with priority, owner, and platform filters. `priority="High", platform_only=True` reproduces the "GOWT High (Platform)" report. |

### Files
| Tool | Description |
|------|-------------|
| `list_files` | List ContentDocuments linked to a record |
| `get_file` | Get file metadata and download URL |
| `download_file` | Download a file's content as base64 (up to 20MB) |
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
| `bulk_query` | Async query for large datasets (supports `include_archived`) |

### OneDrive (GOWT Excel)
| Tool | Description |
|------|-------------|
| `list_onedrive_files` | List files in the GOWT Data Scrape folder |
| `download_onedrive_file` | Download a file as base64 |
| `read_gowt_excel` | Download and parse a GOWT Excel spreadsheet, returning structured data (sheet names, headers, rows) |

### Investment Screener
| Tool | Description |
|------|-------------|
| `get_screener_guide` | Workflow, AA house style and spec format for screeners. Claude calls this first when asked to screen a company |
| `build_screener` | Validate a screener spec against the house rules and build the two-page .docx as a private draft; returns a 24-hour download link for review |
| `approve_screener` | After the user approves a draft, attach that exact file to the Opportunity (becomes a new version if the deal already has one) |
| `create_deal` | Create the Account + Opportunity (team conventions) for a company not yet in Salesforce, at approval time; never duplicates |

### Outreach
| Tool | Description |
|------|-------------|
| `upload_email_attachment` | Upload a file once as a ContentVersion for reuse as a bulk email attachment |
| `bulk_email` | Send individual outreach emails to many Contacts/addresses via Salesforce |

## Archived Activities

Salesforce archives Tasks and Events older than about a year, and normal SOQL does not return them. In this org that is ~75% of Tasks and ~96% of Events, which is most historical meeting notes. `get_notes`, `get_activities` and `get_company_overview` always include archived activities (via `queryAll`) and also match activities rolled up to an Account or linked to a Contact as a non-primary invitee. For raw SOQL on Task/Event, pass `include_archived=True` and filter `IsDeleted = false`.

## Investment Screeners

Ask Claude in plain language, e.g. "screen Acme" or "build a screener from this IM" (attach the IM). Screeners are always drafted, then approved:

1. Claude calls `get_screener_guide`, researches the company (attached documents, Salesforce history, public sources) and calls `build_screener`.
2. Claude replies with a download link to the draft `Screener_Project X.docx` and a short recommendation. Review it in Word.
3. Ask for changes (Claude builds a new draft) or approve ("looks good, upload it").
4. On approval Claude calls `approve_screener`, which attaches the reviewed file to the deal's Opportunity, creating the deal first with `create_deal` if the company is not in Salesforce.

Drafts are stored privately in Salesforce Files, unattached, and served at `/screener-drafts/<token>`: an HMAC-signed link that expires after 24 hours (no API key needed to download). Unapproved drafts are deleted after 7 days. Claude Desktop also lists a `screen` prompt.

The builder lives in `app/screener/` (`guide.md` is the house-style guide Claude follows). To build from a spec locally:

```bash
uv run python -m app.screener app/screener/example_spec.json -o ~/Desktop/
```

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
| `AZURE_TENANT_ID` | Azure AD tenant ID (for OneDrive) |
| `AZURE_CLIENT_ID` | Azure AD app client ID |
| `AZURE_CLIENT_SECRET` | Azure AD app client secret |
| `ONEDRIVE_REFRESH_TOKEN` | OneDrive OAuth2 refresh token |
| `PORT` | Server port (default 8080) |

## Deployment

Hosted on Render (free tier). Auto-deploys on push to `main`.

The Dockerfile builds a Python 3.12 image and runs `python main.py`, which starts a uvicorn server with Streamable HTTP transport on the port specified by the `PORT` env var.

Note: Render free tier sleeps after 15 minutes of inactivity. First request after sleep takes ~30-60s.

## Tech Stack

- **FastMCP** — MCP server framework
- **simple-salesforce** — Salesforce REST API client
- **openpyxl** — Excel file parsing (for GOWT spreadsheets)
- **uvicorn** — ASGI server
- **Starlette** — Auth middleware + status page
- **Render** — hosting (free tier)
