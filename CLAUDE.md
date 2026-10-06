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

**API version:** pinned to Salesforce REST v62.0 in `app/client.py` (`API_VERSION`).

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
│   ├── activities.py    # Archived-aware Task/Event/EmailMessage lookups shared by notes + company tools
│   ├── auth.py          # API key middleware (skips / and /api/uptime)
│   ├── field_map.py     # OPPORTUNITY_FIELD_MAP + OTHER_NOTABLE_FIELDS
│   ├── status.py        # Status page HTML + live uptime API
│   ├── tools/
│   │   ├── __init__.py  # Imports all tool modules to trigger @mcp.tool() registration
│   │   ├── crud.py      # 7 tools: query, query_more, search, get/create/update/delete_record
│   │   ├── metadata.py  # 3 tools: list_objects, describe_object, describe_field
│   │   ├── files.py     # 4 tools: list_files, get_file, download_file, attach_file_link
│   │   ├── reports.py   # 3 tools: list_reports, run_report, list_dashboards
│   │   ├── notes.py     # 5 tools: get_notes, get_activities, get_emails, get_feed, get_field_history
│   │   ├── company.py   # 4 tools: get_company_overview, get_opportunity_field_map, get_related_contacts, get_gowt_opportunities
│   │   ├── bulk.py      # 2 tools: bulk_upsert, bulk_query
│   │   ├── onedrive.py  # 3 tools: list_onedrive_files, download_onedrive_file, read_gowt_excel
│   │   ├── outreach.py  # 2 tools: upload_email_attachment, bulk_email
│   │   └── screener.py  # 4 tools + `screen` prompt: get_screener_guide, create_deal, build_screener, approve_screener
│   └── screener/
│       ├── build.py     # Spec validation + .docx/chart rendering (python -m app.screener)
│       ├── drafts.py    # Signed 24h draft download links + /screener-drafts/{token} route
│       ├── fix_xml.py   # OOXML schema-order repair applied to every build
│       ├── guide.md     # House-style guide returned by get_screener_guide
│       └── example_spec.json
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

## Tools (37)

### Core CRUD (crud.py)

| Tool | Description | Parameters |
|------|-------------|------------|
| `query` | Run arbitrary SOQL, paged | `soql: str, include_archived: bool (default False), max_records: int (default 2000)` |
| `query_more` | Next batch of a paged query | `next_records_url: str, include_archived: bool, max_records: int` |
| `search` | Run SOSL search | `sosl: str` |
| `get_record` | Get a single record | `object_type: str, record_id: str, fields: list[str] (optional)` |
| `create_record` | Create a new record | `object_type: str, data: dict` |
| `update_record` | Update existing record | `object_type: str, record_id: str, data: dict` |
| `delete_record` | Delete a record | `object_type: str, record_id: str` |

### Discovery & Metadata (metadata.py)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_objects` | List all queryable SObjects in the org | `custom_only: bool (default False)` |
| `describe_object` | Get field metadata for an object | `object_type: str` |
| `describe_field` | Get picklist values, field type, etc. | `object_type: str, field_name: str` |

### Notes & Activities (notes.py)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_notes` | Get notes from all sources (Event Descriptions, Task Descriptions, classic Notes, ContentNotes). Primary source of meeting notes (APC notes, NL notes, etc.) | `record_id: str, since: str (optional YYYY-MM-DD), limit: int (default 20)` |
| `get_activities` | Get all Tasks and Events with Descriptions | `record_id: str, include_description: bool (default True), since: str (optional), limit: int (default 200)` |
| `get_emails` | Get EmailMessages for a record | `record_id: str, since: str (optional), limit: int (default 50), include_body: bool (default True), max_body_chars: int (default 5000)` |
| `get_feed` | Get Chatter feed posts with comments | `record_id: str, limit: int (default 50)` |
| `get_field_history` | Get field change history | `object_type: str, record_id: str, limit: int (default 200)` |

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
| `download_file` | Download file content as base64 (max 20MB) | `document_id: str` |
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
| `bulk_query` | Async query for large datasets | `soql: str, include_archived: bool (default False), max_records: int (default 50000)` |

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

The `get_notes` tool searches all four. Events/Tasks are linked via WhatId (Opportunity/Account), AccountId (rolled up from an Account's Opportunities/Contacts), WhoId (primary Contact/Lead, prefixes 003/00Q), or Task/EventRelation (other invitees). `app/activities.py` unions all of these.

**Archived activities:** Salesforce archives Tasks/Events older than ~1 year and hides them from normal SOQL. As of Oct 2026 that is ~73k of ~98k Tasks and ~24k of ~25k Events. All activity lookups must use `queryAll` (`include_deleted=True` in simple-salesforce) with `IsDeleted = false`.

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

## Investment Screeners

Users ask in plain language ("screen Acme"); there is no separate skill to install. Screeners are **always drafted, then approved** by a human before anything is attached to a deal:

1. Claude calls `get_screener_guide` (returns `app/screener/guide.md` + `example_spec.json`)
2. Gathers attached IM/CIM, Salesforce history (`search`, `get_company_overview`, `get_notes`, `get_emails`) and public research
3. Writes the spec JSON and calls `build_screener(spec)`. Validation errors come back without building; Claude fixes and retries
4. The .docx is saved as an unattached ContentVersion (Description `AA screener draft`, visible only to the integration user) and Claude replies with a signed download link: `/screener-drafts/<token>`, HMAC over ContentDocumentId + expiry (24h), key from `DRAFT_LINK_SECRET` or derived from `CONSUMER_SECRET`. The route is exempt from API-key auth
5. On the user's explicit approval, `approve_screener(draft_id, opportunity_id)` links that exact file to the Opportunity (Description becomes `AA screener`), or adds it as a new version if the deal already has a file with the same title. If the company is not in Salesforce, `create_deal` runs first (stage `4. Medium`, CloseDate 2049-01-01, industry `fid8__c`, location `fid5__c`, source type `fid10__c`, discussion status `fid31__c`, `fidprocesscreateddate__c` now)
6. Unapproved drafts older than 7 days are deleted on the next build

**House format:** two pages, A4, AA colours, combo chart + revenue-mix donut + chart notes, fixed thesis (2 category headers, 5 criteria, confirmed against Dark Horse, Silver Wolf and CoolDrive screeners) and Porter tables. Reference standard is `Screener_Project Bundaberg.docx` (Sep-2026). Charts use Calibri when present, else Carlito (installed in the Docker image).
