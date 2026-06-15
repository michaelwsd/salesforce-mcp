# Salesforce MCP — Build Specification

## Purpose

A remote MCP server that gives Claude (and any MCP client) full CRUD access to the Armitage Salesforce org. This is general-purpose infrastructure used across the origination workflow — the screener skill, meeting prep, IC memo generation, and any future workflow that needs Salesforce data.

---

## Architecture

```
Claude Desktop / Skill / Agent
        │
        ▼  (Streamable HTTP)
┌──────────────────────────┐
│   Salesforce MCP Server  │
│   FastMCP + Python       │
│   Hosted on Fly.io       │
└──────────┬───────────────┘
           │  (REST API v62.0)
           ▼
┌──────────────────────────┐
│   Armitage Salesforce    │
│   Org                    │
└──────────────────────────┘
```

**Transport:** Streamable HTTP (recommended over SSE for remote servers). Endpoint mounted at `/mcp` by default.

**Framework:** FastMCP (Python SDK) — tools defined as decorated functions, schema auto-generated from type hints.

**Hosting:** Fly.io free tier (256MB RAM, always-on, no cold starts). Single process running uvicorn.

---

## Authentication

### Salesforce Auth (server → Salesforce)

OAuth2 client credentials flow, same pattern as the existing `armitage-outreach-automation` repo. Credentials stored as environment variables on the hosting platform.

| Variable | Purpose |
|----------|---------|
| `SALESFORCE_DOMAIN` | Instance URL (e.g. `https://armitage.my.salesforce.com`) |
| `CONSUMER_KEY` | Connected App consumer key |
| `CONSUMER_SECRET` | Connected App consumer secret |
| `SALESFORCE_USERNAME` | Login email |
| `SALESFORCE_PASSWORD` | Password |
| `SALESFORCE_SECURITY_TOKEN` | Security token |

Token is cached in memory and refreshed on expiry. Use `simple-salesforce` library for all API calls.

### MCP Auth (client → MCP server)

API key passed as a bearer token in the HTTP header. Each team member gets a key. This prevents unauthorised access to the server.

---

## Tools to Expose

### Core CRUD

| Tool | Description | Parameters |
|------|-------------|------------|
| `query` | Run arbitrary SOQL | `soql: str` |
| `search` | Run SOSL search | `sosl: str` |
| `get_record` | Get a single record | `object_type: str, record_id: str, fields: list[str] (optional)` |
| `create_record` | Create a new record | `object_type: str, data: dict` |
| `update_record` | Update existing record | `object_type: str, record_id: str, data: dict` |
| `delete_record` | Delete a record | `object_type: str, record_id: str` |

### Discovery & Metadata

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_objects` | List all SObjects in the org | None |
| `describe_object` | Get field metadata for an object | `object_type: str` |
| `describe_field` | Get picklist values, field type, etc. | `object_type: str, field_name: str` |

### Reports & Dashboards

| Tool | Description | Parameters |
|------|-------------|------------|
| `run_report` | Execute a Salesforce report by ID | `report_id: str, filters: dict (optional)` |
| `list_dashboards` | List available dashboards | None |

### File Operations

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_files` | List ContentDocuments linked to a record | `record_id: str` |
| `get_file` | Download a file by ContentDocument ID | `document_id: str` |
| `attach_file_link` | Create a ContentVersion linked to a record with an external URL | `record_id: str, url: str, title: str` |

Note: actual file storage is external (S3 or Google Drive). Salesforce holds reference URLs via `attach_file_link`. The upload-to-S3 step is handled by a separate storage tool or the screener skill itself.

### Bulk Operations

| Tool | Description | Parameters |
|------|-------------|------------|
| `bulk_upsert` | Upsert multiple records | `object_type: str, external_id_field: str, records: list[dict]` |
| `bulk_query` | Async query for large datasets | `soql: str` |

---

## Key Salesforce Objects

Based on the existing outreach-automation repo, these are the primary objects the MCP needs to interact with:

| Object | Usage in Workflow |
|--------|-------------------|
| `Opportunity` | Core deal record — stages, values, owners |
| `Account` | Company record — name, industry, location |
| `Contact` | People — founders, management, advisors |
| `OpportunityContactRole` | Links contacts to opportunities (primary contact lookup) |
| `ContentDocument` / `ContentVersion` | Attached files (CIMs, IMs, screeners) |
| `Task` / `Event` | Meeting notes, follow-ups |
| `Growth_News__c` | Custom field — growth signals from outreach automation |
| `Growth_Actions__c` | Custom field — AI-generated action items |
| `P__c` | Custom field — contact LinkedIn activity |

The MCP should work with any object, not just these — the tools are generic.

---

## Screener Skill Integration

The screener skill is the first consumer of this MCP. The flow:

```
User: "Build the screener for Total Essential Services Group"
                │
                ▼
┌─────────────────────────────────────────┐
│  Screener Skill                         │
│                                         │
│  1. Call MCP: query Salesforce for      │
│     company data (Account, Opportunity, │
│     Contacts, notes, activity history)  │
│                                         │
│  2. Call MCP: list_files to find any    │
│     existing docs linked to the record  │
│                                         │
│  3. Accept user-uploaded docs           │
│     (CIM, IM, financials — PDF, DOCX,  │
│     PPTX)                              │
│                                         │
│  4. Extract text from all sources       │
│     - PDF → pdftotext                   │
│     - DOCX → pandoc                     │
│     - PPTX → python-pptx               │
│                                         │
│  5. Convert all docs to page images     │
│     - PDF → pdftoppm                    │
│     - DOCX/PPTX → LibreOffice → PDF    │
│       → pdftoppm                        │
│                                         │
│  6. Claude visually scans page images,  │
│     identifies charts/tables relevant   │
│     to screener sections, returns crop  │
│     coordinates                         │
│                                         │
│  7. Crop images (Pillow) and insert     │
│     into screener template              │
│                                         │
│  8. Populate screener sections:         │
│     - Business overview (from CIM text  │
│       + Salesforce data)                │
│     - Financial overview (text + cropped│
│       charts)                           │
│     - Transaction dynamics (SF notes +  │
│       CIM)                              │
│     - Investment thesis criteria (AI    │
│       scored Y/N/? with reasoning)      │
│     - Porter's Five Forces (AI rated    │
│       L/M/H with commentary)           │
│                                         │
│  9. Generate completed .docx            │
│                                         │
│ 10. Upload to S3/GDrive, call MCP:     │
│     attach_file_link to Salesforce      │
└─────────────────────────────────────────┘
```

---

## Screener Template Sections

The screener (based on the Total Essential Services Group example) has five sections. Each has different automation characteristics:

| Section | Auto-populated from | AI confidence | Human review needed |
|---------|---------------------|---------------|---------------------|
| Business & Industry Overview | CIM text, Salesforce Account fields, web research | High | Light edit |
| Financial Overview | CIM financials, cropped charts from uploaded docs | High (text), Medium (chart selection) | Verify chart relevance |
| Transaction Dynamics & Recommendation | Salesforce notes, CIM deal section | Medium | Yes — recommendation is a human call |
| Investment Thesis Criteria | All sources — AI scores Y/N/? per criterion | Medium | Yes — validate judgement calls |
| Porter's Five Forces | CIM + web research — AI rates L/M/H | Medium | Yes — analyst overlay |

---

## Technical Stack

| Component | Technology |
|-----------|------------|
| MCP framework | FastMCP (Python SDK) |
| Salesforce client | `simple-salesforce` |
| Transport | Streamable HTTP (`/mcp` endpoint) |
| ASGI server | uvicorn |
| Hosting | Fly.io (free tier, 256MB RAM) |
| Auth | Bearer token (API key per user) |
| Python version | 3.12+ |

### Dependencies

```
mcp[cli]
simple-salesforce
uvicorn
```

---

## Server Skeleton

```python
from mcp.server.fastmcp import FastMCP
from simple_salesforce import Salesforce
import os

mcp = FastMCP("Armitage Salesforce", stateless_http=True)

def get_sf_client():
    return Salesforce(
        username=os.environ["SALESFORCE_USERNAME"],
        password=os.environ["SALESFORCE_PASSWORD"],
        security_token=os.environ["SALESFORCE_SECURITY_TOKEN"],
        consumer_key=os.environ["CONSUMER_KEY"],
        consumer_secret=os.environ["CONSUMER_SECRET"],
        domain=os.environ.get("SALESFORCE_DOMAIN", "login"),
    )

@mcp.tool()
def query(soql: str) -> dict:
    """Run a SOQL query against Salesforce. Returns matching records."""
    sf = get_sf_client()
    return sf.query_all(soql)

@mcp.tool()
def get_record(object_type: str, record_id: str) -> dict:
    """Get a single Salesforce record by object type and ID."""
    sf = get_sf_client()
    obj = getattr(sf, object_type)
    return obj.get(record_id)

@mcp.tool()
def create_record(object_type: str, data: dict) -> dict:
    """Create a new Salesforce record."""
    sf = get_sf_client()
    obj = getattr(sf, object_type)
    return obj.create(data)

@mcp.tool()
def update_record(object_type: str, record_id: str, data: dict) -> dict:
    """Update an existing Salesforce record."""
    sf = get_sf_client()
    obj = getattr(sf, object_type)
    return obj.update(record_id, data)

@mcp.tool()
def delete_record(object_type: str, record_id: str) -> dict:
    """Delete a Salesforce record."""
    sf = get_sf_client()
    obj = getattr(sf, object_type)
    return obj.delete(record_id)

@mcp.tool()
def describe_object(object_type: str) -> dict:
    """Get field metadata for a Salesforce object."""
    sf = get_sf_client()
    obj = getattr(sf, object_type)
    return obj.describe()

@mcp.tool()
def list_files(record_id: str) -> dict:
    """List all files (ContentDocuments) linked to a Salesforce record."""
    sf = get_sf_client()
    return sf.query(
        f"SELECT ContentDocumentId, ContentDocument.Title, "
        f"ContentDocument.FileType, ContentDocument.ContentSize "
        f"FROM ContentDocumentLink "
        f"WHERE LinkedEntityId = '{record_id}'"
    )

# Add remaining tools following the same pattern...

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8080)
```

---

## Deployment (Fly.io)

### fly.toml

```toml
app = "armitage-salesforce-mcp"

[build]
  builder = "paketobuildpacks/builder:base"

[env]
  PORT = "8080"

[http_service]
  internal_port = 8080
  force_https = true

[[vm]]
  memory = "256mb"
  cpu_kind = "shared"
  cpus = 1
```

### Deploy

```bash
fly launch
fly secrets set SALESFORCE_USERNAME=... CONSUMER_KEY=... # etc.
fly deploy
```

### Connect from Claude Desktop

Add to Claude Desktop MCP config:

```json
{
  "mcpServers": {
    "armitage-salesforce": {
      "url": "https://armitage-salesforce-mcp.fly.dev/mcp",
      "headers": {
        "Authorization": "Bearer <API_KEY>"
      }
    }
  }
}
```

---

## Security Considerations

- **Salesforce permissions:** The connected app should use a dedicated integration user with a permission set scoped to the objects/fields the workflow needs. Do not use an admin account.
- **API key rotation:** Support multiple valid API keys so team members can be revoked individually.
- **Query guardrails:** Consider adding a `LIMIT` clause to unbounded SOQL queries to prevent accidental full-table scans.
- **Audit logging:** Log all write operations (create, update, delete) with the API key used and timestamp.
- **No credentials in code:** All secrets via environment variables on Fly.io.

---

## Build Order

1. **MCP server with core CRUD + query tools** — get basic read/write working
2. **Add describe/metadata tools** — so Claude can discover schema
3. **Add file operations** — list and link files to records
4. **Add report/dashboard tools** — for GOWT dashboard access
5. **Add bulk operations** — for batch updates
6. **Deploy to Fly.io** — remote access for the team
7. **Build screener skill** — first consumer of the MCP
8. **Iterate** — add tools as new workflow steps need them

---

## References

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [FastMCP docs](https://gofastmcp.com/deployment/running-server)
- [simple-salesforce](https://github.com/simple-salesforce/simple-salesforce)
- [Salesforce REST API](https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/)
- [Fly.io deployment](https://fly.io/docs/languages-and-frameworks/python/)
- [Existing outreach-automation repo](https://github.com/armitage-associates/armitage-outreach-automation)