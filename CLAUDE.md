# Salesforce MCP — Build Specification

## Purpose

A remote MCP server that gives Claude (and any MCP client) full CRUD access to the Armitage Salesforce org and GOWT Excel data on OneDrive. This is general-purpose infrastructure used across the origination workflow — the screener skill, meeting prep, IC memo generation, and any future workflow that needs Salesforce data.

---

## Architecture

```
Claude Desktop / Skill / Agent
        │
        ▼  (Streamable HTTP)
┌──────────────────────────┐
│   Salesforce MCP Server  │
│   FastMCP + Python       │
│   Hosted on Render       │
└──────────┬───────────────┘
           │
           ├── (REST API v62.0) ──▶ Armitage Salesforce Org
           │
           └── (Microsoft Graph) ──▶ OneDrive / GOWT Data Scrape
```

**Transport:** Streamable HTTP. Endpoint at `/mcp`. Status page at `/`.

**Framework:** FastMCP (Python SDK) — tools defined as decorated functions, schema auto-generated from type hints.

**Hosting:** Render free tier (512MB RAM, sleeps after 15min inactivity). Single process running uvicorn.

---

## Project Structure

```
salesforce-mcp/
├── main.py              # Entry point — starts uvicorn, adds auth + status route
├── Dockerfile
├── pyproject.toml
├── app/
│   ├── __init__.py      # FastMCP instance + logging + tool registration
│   ├── client.py        # Salesforce OAuth2 connection (get_sf_client)
│   ├── auth.py          # API key middleware (skips / and /api/uptime)
│   ├── field_map.py     # OPPORTUNITY_FIELD_MAP + OTHER_NOTABLE_FIELDS
│   ├── status.py        # Status page HTML + live uptime API
│   └── tools/
│       ├── __init__.py  # Imports all tool modules to trigger @mcp.tool() registration
│       ├── crud.py      # 6 tools: query, search, get/create/update/delete_record
│       ├── metadata.py  # 3 tools: list_objects, describe_object, describe_field
│       ├── files.py     # 3 tools: list_files, get_file, attach_file_link
│       ├── reports.py   # 3 tools: list_reports, run_report, list_dashboards
│       ├── notes.py     # 4 tools: get_notes, get_activities, get_feed, get_field_history
│       ├── company.py   # 4 tools: get_company_overview, get_opportunity_field_map, get_related_contacts, get_gowt_opportunities
│       ├── bulk.py      # 2 tools: bulk_upsert, bulk_query
│       └── onedrive.py  # 3 tools: list_onedrive_files, download_onedrive_file, read_gowt_excel
```

---

## Authentication

### Salesforce Auth (server → Salesforce)

OAuth2 client credentials flow, same pattern as the `armitage-deployed` repo. Credentials stored as environment variables on Render.

| Variable | Purpose |
|----------|---------|
| `SALESFORCE_DOMAIN` | Instance URL |
| `CONSUMER_KEY` | Connected App consumer key |
| `CONSUMER_SECRET` | Connected App consumer secret |
| `SALESFORCE_USERNAME` | Login email (fallback auth) |
| `SALESFORCE_PASSWORD` | Password (fallback auth) |
| `SALESFORCE_SECURITY_TOKEN` | Security token (fallback auth) |

### OneDrive Auth (server → Microsoft Graph)

OAuth2 refresh token flow, same credentials as `armitage-deployed`.

| Variable | Purpose |
|----------|---------|
| `AZURE_TENANT_ID` | Azure AD tenant ID |
| `AZURE_CLIENT_ID` | Azure AD app client ID |
| `AZURE_CLIENT_SECRET` | Azure AD app client secret |
| `ONEDRIVE_REFRESH_TOKEN` | OAuth2 refresh token (expires after 90 days of inactivity) |

### MCP Auth (client → MCP server)

API key passed as Bearer token in HTTP header. Each team member gets a key. The `/` status page and `/api/uptime` endpoint are public (no auth required).

| Variable | Purpose |
|----------|---------|
| `MCP_API_KEYS` | Comma-separated valid API keys |

---

## Tools (28)

### Core CRUD (crud.py)

| Tool | Description | Parameters |
|------|-------------|------------|
| `query` | Run arbitrary SOQL | `soql: str` |
| `search` | Run SOSL search | `sosl: str` |
| `get_record` | Get a single record | `object_type: str, record_id: str, fields: list[str] (optional)` |
| `create_record` | Create a new record | `object_type: str, data: dict` |
| `update_record` | Update existing record | `object_type: str, record_id: str, data: dict` |
| `delete_record` | Delete a record | `object_type: str, record_id: str` |

### Discovery & Metadata (metadata.py)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_objects` | List all SObjects in the org | None |
| `describe_object` | Get field metadata for an object | `object_type: str` |
| `describe_field` | Get picklist values, field type, etc. | `object_type: str, field_name: str` |

### Notes & Activities (notes.py)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_notes` | Get notes from all sources (Event Descriptions, Task Descriptions, classic Notes, ContentNotes). Primary source of meeting notes (APC notes, NL notes, etc.) | `record_id: str, since: str (optional YYYY-MM-DD), limit: int (default 20)` |
| `get_activities` | Get all Tasks and Events with Descriptions | `record_id: str, include_description: bool (default True)` |
| `get_feed` | Get Chatter feed posts | `record_id: str` |
| `get_field_history` | Get field change history | `object_type: str, record_id: str` |

### Company Deep-Dive (company.py)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_company_overview` | Pull everything for an Opportunity | `opportunity_id: str` |
| `get_opportunity_field_map` | Get fid → readable name mapping | None |
| `get_related_contacts` | Get contacts via OCR or Account | `record_id: str` |
| `get_gowt_opportunities` | Get GOWT pipeline deals. `priority="High", platform_only=True` = "GOWT High (Platform)" report | `priority: str (optional), owner: str (optional), platform_only: bool (default False)` |

### Files (files.py)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_files` | List ContentDocuments linked to a record | `record_id: str` |
| `get_file` | Get file metadata and download URL | `document_id: str` |
| `attach_file_link` | Link an external URL to a record | `record_id: str, url: str, title: str` |

### Reports & Dashboards (reports.py)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_reports` | List all reports | None |
| `run_report` | Execute a report by ID | `report_id: str, filters: dict (optional)` |
| `list_dashboards` | List all dashboards | None |

### Bulk Operations (bulk.py)

| Tool | Description | Parameters |
|------|-------------|------------|
| `bulk_upsert` | Upsert multiple records | `object_type: str, external_id_field: str, records: list[dict]` |
| `bulk_query` | Async query for large datasets | `soql: str` |

### OneDrive / GOWT Excel (onedrive.py)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_onedrive_files` | List files in GOWT Data Scrape folder | None |
| `download_onedrive_file` | Download a file as base64 | `filename: str` |
| `read_gowt_excel` | Parse a GOWT Excel spreadsheet into structured data | `filename: str, sheet_name: str (optional), max_rows: int (default 100)` |

**OneDrive files:**
- `GOWT_high.xlsx` — one tab per GOWT High company with LinkedIn posts (updated monthly by `armitage-deployed`)
- `GOWT_mid_low.xlsx` — FTE Tracking sheet + quarterly news sheets (updated quarterly by `armitage-deployed`)

---

## Key Salesforce Objects

| Object | Usage in Workflow |
|--------|-------------------|
| `Opportunity` | Core deal record — stages, values, owners |
| `Account` | Company record — name, industry, location |
| `Contact` | People — founders, management, advisors |
| `OpportunityContactRole` | Links contacts to opportunities (primary contact lookup) |
| `ContentDocument` / `ContentVersion` | Attached files (CIMs, IMs, screeners) |
| `Task` / `Event` | Meeting notes, follow-ups (notes in Description field) |
| `Growth_Summary__c` | LinkedIn news and AI-generated action items |

### Key Opportunity Stages

| Stage | Meaning |
|-------|---------|
| `8. Good opportunity wrong timing` | GOWT pipeline — tracked by priority (Ultra High/High/Medium/Low) |
| `7. Killed` | Dead deals |

### GOWT Report Filters

"GOWT High (Platform)" = `StageName = '8. Good opportunity wrong timing' AND GOWT_Priority__c = 'High' AND Transaction_type__c != '8. Portfolio company bolt-on'` (24 records as of June 2026).

### Legacy Field Names

Many Opportunity fields have cryptic `fid` names from the SalesforceIQ migration. The mapping is in `app/field_map.py`. Key fields:
- `fid14__c` → Revenue estimate ($M)
- `fid15__c` → EBITDA estimate ($M)
- `fid17__c` → EV estimate ($M)
- `fid8__c` → Industry
- `fid53__c` → GOWT Owner (e.g. APC, NL, DG, BO, MY, HM, LF)

### Where Notes Live

Notes in this org are scattered across four places:
1. **Event.Description** — primary source (APC notes, NL notes, meeting summaries)
2. **Task.Description** — follow-up notes, call logs
3. **Note** — classic notes linked via ParentId
4. **ContentNote** — enhanced notes linked via ContentDocumentLink

The `get_notes` tool searches all four. Events/Tasks are linked via WhatId (Opportunity/Account) or WhoId (Contact/Lead — prefixes 003/00Q).

---

## Deployment

### Render (current)

Hosted on Render free tier. Auto-deploys from GitHub `main` branch.

- **URL:** https://salesforce-mcp-cq58.onrender.com/mcp
- **Status page:** https://salesforce-mcp-cq58.onrender.com/
- **Free tier limits:** 750hrs/month, 512MB RAM, sleeps after 15min inactivity

### Connect from Claude Desktop

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

---

## Technical Stack

| Component | Technology |
|-----------|------------|
| MCP framework | FastMCP (Python SDK) |
| Salesforce client | `simple-salesforce` |
| Excel parsing | `openpyxl` |
| OneDrive API | Microsoft Graph v1.0 (OAuth2 refresh token) |
| Transport | Streamable HTTP (`/mcp` endpoint) |
| ASGI server | uvicorn |
| Auth | Bearer token middleware (Starlette) |
| Hosting | Render (free tier) |
| Python | 3.12+ |

---

## Related Repos

- **armitage-deployed** — LinkedIn scraper + GOWT Excel generation + OneDrive upload. Runs on GitHub Actions (monthly High, quarterly Medium/Low, quarterly FTE). Uses same Salesforce + OneDrive credentials.

---

## Screener Skill Integration

The screener skill is the first consumer of this MCP. The flow:

1. Query Salesforce for company data (Account, Opportunity, Contacts, notes, activity history)
2. List files linked to the record
3. Accept user-uploaded docs (CIM, IM, financials)
4. Extract text + page images from docs
5. Claude identifies relevant charts/tables
6. Populate screener template sections
7. Generate completed .docx
8. Upload to storage, link to Salesforce via `attach_file_link`

### Screener Sections

| Section | Sources | AI Confidence |
|---------|---------|---------------|
| Business & Industry Overview | CIM text, SF Account, web research | High |
| Financial Overview | CIM financials, cropped charts | Medium-High |
| Transaction Dynamics & Recommendation | SF notes, CIM deal section | Medium |
| Investment Thesis Criteria | All sources — Y/N/? per criterion | Medium |
| Porter's Five Forces | CIM + web research — L/M/H | Medium |
