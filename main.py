import os
import logging
import hmac
import requests
from dotenv import load_dotenv
from simple_salesforce import Salesforce
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from mcp.server.fastmcp import FastMCP

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# --- FastMCP app ---
# This creates the MCP server instance.
# stateless_http=True means each request is independent — no session state
# is kept between calls. This is simpler and works well on Fly.io where
# your server might restart at any time.
mcp = FastMCP(
    "Armitage Salesforce",
    stateless_http=True,
    host="0.0.0.0",
    port=8080,
)


# --- Salesforce connection ---

def get_sf_client() -> Salesforce:
    """Create an authenticated Salesforce client.

    Uses OAuth2 client credentials flow (same as armitage-deployed).
    Falls back to username/password if client credentials aren't set.
    """
    domain = os.environ["SALESFORCE_DOMAIN"]
    consumer_key = os.getenv("CONSUMER_KEY")
    consumer_secret = os.getenv("CONSUMER_SECRET")

    if consumer_key and consumer_secret:
        token_response = requests.post(
            f"{domain}/services/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": consumer_key,
                "client_secret": consumer_secret,
            },
        )
        token_response.raise_for_status()
        access_token = token_response.json()["access_token"]
        return Salesforce(instance_url=domain, session_id=access_token)

    return Salesforce(
        username=os.environ["SALESFORCE_USERNAME"],
        password=os.environ["SALESFORCE_PASSWORD"],
        security_token=os.environ["SALESFORCE_SECURITY_TOKEN"],
        consumer_key=consumer_key or "",
        consumer_secret=consumer_secret or "",
    )


# =============================================================================
# CORE CRUD TOOLS
# =============================================================================
# These are the fundamental operations: query, search, get, create, update, delete.
# Every other workflow (screener, outreach, meeting prep) builds on top of these.
# =============================================================================

@mcp.tool()
def query(soql: str) -> dict:
    """Run a SOQL query against Salesforce.

    SOQL (Salesforce Object Query Language) is like SQL but for Salesforce.
    Example: SELECT Id, Name, StageName FROM Opportunity WHERE StageName != '7. Killed' LIMIT 10

    Returns all matching records, automatically handling pagination for large result sets.
    """
    sf = get_sf_client()
    return sf.query_all(soql)


@mcp.tool()
def search(sosl: str) -> dict:
    """Run a SOSL search across multiple Salesforce objects.

    SOSL (Salesforce Object Search Language) is a full-text search across
    multiple objects at once. Use this when you want to find something but
    don't know which object it's in.

    Example: FIND {Armitage} IN ALL FIELDS RETURNING Account(Name), Contact(Name, Email)
    """
    sf = get_sf_client()
    return sf.search(sosl)


@mcp.tool()
def get_record(object_type: str, record_id: str, fields: list[str] | None = None) -> dict:
    """Get a single Salesforce record by its object type and ID.

    Args:
        object_type: The Salesforce object type (e.g. Account, Opportunity, Contact)
        record_id: The 18-character Salesforce record ID
        fields: Optional list of specific fields to return. If omitted, returns all fields.
    """
    sf = get_sf_client()
    if fields:
        field_list = ", ".join(fields)
        result = sf.query(
            f"SELECT {field_list} FROM {object_type} WHERE Id = '{record_id}'"
        )
        return result["records"][0] if result["records"] else {"error": "Record not found"}
    sobject = getattr(sf, object_type)
    return sobject.get(record_id)


@mcp.tool()
def create_record(object_type: str, data: dict) -> dict:
    """Create a new Salesforce record.

    Args:
        object_type: The Salesforce object type (e.g. Account, Contact, Task)
        data: Dictionary of field names and values. Field names must match the API names
              in Salesforce (e.g. "Name", "StageName", "Growth_News__c").
    """
    sf = get_sf_client()
    sobject = getattr(sf, object_type)
    result = sobject.create(data)
    logger.info(f"Created {object_type} record: {result}")
    return result


@mcp.tool()
def update_record(object_type: str, record_id: str, data: dict) -> dict:
    """Update an existing Salesforce record.

    Args:
        object_type: The Salesforce object type
        record_id: The 18-character Salesforce record ID
        data: Dictionary of field names and new values to set
    """
    sf = get_sf_client()
    sobject = getattr(sf, object_type)
    result = sobject.update(record_id, data)
    logger.info(f"Updated {object_type} {record_id}: {data}")
    return result


@mcp.tool()
def delete_record(object_type: str, record_id: str) -> dict:
    """Delete a Salesforce record.

    Args:
        object_type: The Salesforce object type
        record_id: The 18-character Salesforce record ID
    """
    sf = get_sf_client()
    sobject = getattr(sf, object_type)
    result = sobject.delete(record_id)
    logger.info(f"Deleted {object_type} {record_id}")
    return result


# =============================================================================
# DISCOVERY & METADATA TOOLS
# =============================================================================
# These let Claude explore the Salesforce schema — what objects exist, what
# fields they have, what picklist values are available. This is essential
# because Claude doesn't know your org's custom fields ahead of time.
# =============================================================================

@mcp.tool()
def list_objects() -> list[dict]:
    """List all SObjects (object types) available in the Salesforce org.

    Returns the name and label of each object. Use this to discover what
    objects exist before querying them.
    """
    sf = get_sf_client()
    description = sf.describe()
    return [
        {"name": obj["name"], "label": obj["label"], "custom": obj["custom"]}
        for obj in description["sobjects"]
        if obj["queryable"]
    ]


@mcp.tool()
def describe_object(object_type: str) -> list[dict]:
    """Get field metadata for a Salesforce object.

    Returns the name, label, type, and whether each field is required.
    Use this to understand what fields are available before querying or
    creating records.

    Args:
        object_type: The Salesforce object type (e.g. Opportunity, Account)
    """
    sf = get_sf_client()
    sobject = getattr(sf, object_type)
    description = sobject.describe()
    return [
        {
            "name": f["name"],
            "label": f["label"],
            "type": f["type"],
            "required": not f["nillable"] and not f["defaultedOnCreate"],
            "custom": f["custom"],
        }
        for f in description["fields"]
    ]


@mcp.tool()
def describe_field(object_type: str, field_name: str) -> dict:
    """Get detailed metadata for a specific field, including picklist values.

    Use this when you need to know the allowed values for a picklist field,
    the field's data type, length constraints, or relationship details.

    Args:
        object_type: The Salesforce object type
        field_name: The API name of the field (e.g. StageName, GOWT_Priority__c)
    """
    sf = get_sf_client()
    sobject = getattr(sf, object_type)
    description = sobject.describe()
    for field in description["fields"]:
        if field["name"] == field_name:
            result = {
                "name": field["name"],
                "label": field["label"],
                "type": field["type"],
                "length": field.get("length"),
                "required": not field["nillable"] and not field["defaultedOnCreate"],
                "updateable": field["updateable"],
                "custom": field["custom"],
            }
            if field.get("picklistValues"):
                result["picklist_values"] = [
                    {"value": pv["value"], "label": pv["label"], "active": pv["active"]}
                    for pv in field["picklistValues"]
                ]
            if field.get("referenceTo"):
                result["references"] = field["referenceTo"]
            return result
    return {"error": f"Field '{field_name}' not found on {object_type}"}


# =============================================================================
# FILE OPERATIONS
# =============================================================================
# Salesforce stores files as ContentDocument/ContentVersion objects.
# Files are linked to records (Opportunities, Accounts, etc.) via
# ContentDocumentLink — a junction object that connects a file to a record.
# =============================================================================

@mcp.tool()
def list_files(record_id: str) -> dict:
    """List all files (ContentDocuments) linked to a Salesforce record.

    Returns the file title, type, and size for each attached document.
    Use this to find CIMs, IMs, screeners, or other docs linked to
    an Opportunity or Account.

    Args:
        record_id: The ID of the record to list files for (e.g. an Opportunity ID)
    """
    sf = get_sf_client()
    return sf.query(
        "SELECT ContentDocumentId, ContentDocument.Title, "
        "ContentDocument.FileType, ContentDocument.ContentSize "
        "FROM ContentDocumentLink "
        f"WHERE LinkedEntityId = '{record_id}'"
    )


@mcp.tool()
def get_file(document_id: str) -> dict:
    """Get file metadata and download URL for a ContentDocument.

    Returns the file's latest version info including title, type, and
    a download path you can use to fetch the file content.

    Args:
        document_id: The ContentDocument ID (starts with 069)
    """
    sf = get_sf_client()
    version = sf.query(
        "SELECT Id, Title, FileType, ContentSize, VersionData "
        "FROM ContentVersion "
        f"WHERE ContentDocumentId = '{document_id}' "
        "AND IsLatest = true"
    )
    if not version["records"]:
        return {"error": f"No version found for document {document_id}"}
    record = version["records"][0]
    return {
        "id": record["Id"],
        "title": record["Title"],
        "file_type": record["FileType"],
        "size": record["ContentSize"],
        "download_path": f"{sf.base_url}{record['VersionData']}",
    }


@mcp.tool()
def attach_file_link(record_id: str, url: str, title: str) -> dict:
    """Attach an external file link to a Salesforce record.

    Creates a ContentVersion with an external URL and links it to the record.
    Use this after uploading a file to S3 or Google Drive to create a
    reference in Salesforce.

    Args:
        record_id: The record to link the file to (e.g. an Opportunity ID)
        url: The external URL where the file is hosted
        title: Display title for the file in Salesforce
    """
    sf = get_sf_client()
    version = sf.ContentVersion.create({
        "Title": title,
        "PathOnClient": title,
        "ExternalDataSourceId": None,
        "ContentUrl": url,
    })
    version_id = version["id"]

    content_doc = sf.query(
        f"SELECT ContentDocumentId FROM ContentVersion WHERE Id = '{version_id}'"
    )
    doc_id = content_doc["records"][0]["ContentDocumentId"]

    sf.ContentDocumentLink.create({
        "ContentDocumentId": doc_id,
        "LinkedEntityId": record_id,
        "ShareType": "V",
    })

    logger.info(f"Attached '{title}' to record {record_id}")
    return {"content_document_id": doc_id, "content_version_id": version_id}


# =============================================================================
# REPORTS & DASHBOARDS
# =============================================================================
# Salesforce has a built-in reporting engine. Reports are pre-built queries
# with filters, groupings, and charts. The Analytics API lets us run them
# programmatically — useful for pulling GOWT dashboard data.
# =============================================================================

@mcp.tool()
def list_reports() -> dict:
    """List all reports in the Salesforce org.

    Returns report names and IDs. Use the ID with run_report to execute one.
    """
    sf = get_sf_client()
    return sf.query("SELECT Id, Name, FolderName FROM Report ORDER BY Name")


@mcp.tool()
def run_report(report_id: str, filters: dict | None = None) -> dict:
    """Execute a Salesforce report and return its results.

    Args:
        report_id: The 15 or 18 character report ID
        filters: Optional report filter overrides
    """
    sf = get_sf_client()
    body = {"reportMetadata": filters} if filters else {"reportMetadata": {}}
    return sf.restful(f"analytics/reports/{report_id}", method="POST", json=body)


@mcp.tool()
def list_dashboards() -> list[dict]:
    """List all dashboards in the Salesforce org.

    Returns dashboard names and IDs.
    """
    sf = get_sf_client()
    result = sf.restful("analytics/dashboards")
    if isinstance(result, list):
        return result
    return result.get("dashboards", [])


# =============================================================================
# NOTES & ACTIVITY TOOLS
# =============================================================================
# Notes in Salesforce are scattered across multiple objects:
# - Note: classic notes (Title + Body text, linked via ParentId)
# - ContentNote: enhanced notes (rich text, linked via ContentDocumentLink)
# - Task: meeting notes, follow-ups, to-dos (notes in Description field)
# - Event: meetings, calls (notes in Description field)
# - FeedItem / OpportunityFeed: Chatter posts on records
# These tools pull them all together so Claude gets the full picture.
# =============================================================================


@mcp.tool()
def get_notes(record_id: str, since: str | None = None, limit: int = 20) -> dict:
    """Get notes and meeting notes for a Salesforce record.

    In this org, meeting notes are stored as Event Descriptions (e.g. "APC notes"
    events with detailed bullet points). This tool searches everywhere notes
    can live:

    1. Event Descriptions — primary source of meeting notes (APC notes, NL notes, etc.)
    2. Task Descriptions — follow-up notes and call logs
    3. Classic Notes — legacy Note objects linked via ParentId
    4. ContentNotes — enhanced notes linked via ContentDocumentLink

    Always call this tool when asked about notes for a company or deal.

    Args:
        record_id: The ID of the record (Opportunity, Account, Contact, or Lead)
        since: Optional date filter — only return notes from this date onwards.
               Format: YYYY-MM-DD (e.g. "2026-01-01"). Use this for "recent notes",
               "notes from last month", etc.
        limit: Maximum number of notes to return per category (default 20)
    """
    sf = get_sf_client()

    prefix = record_id[:3]
    is_who = prefix in ("003", "00Q")

    if is_who:
        link_filter = f"WhoId = '{record_id}'"
    else:
        link_filter = f"WhatId = '{record_id}'"

    date_filter_event = f" AND StartDateTime >= {since}T00:00:00Z" if since else ""
    date_filter_task = f" AND ActivityDate >= {since}" if since else ""
    date_filter_note = f" AND CreatedDate >= {since}T00:00:00Z" if since else ""

    events = sf.query(
        f"SELECT Id, Subject, StartDateTime, Description, Owner.Name "
        f"FROM Event WHERE {link_filter}{date_filter_event} "
        f"ORDER BY StartDateTime DESC NULLS LAST LIMIT {limit}"
    )

    tasks = sf.query(
        f"SELECT Id, Subject, ActivityDate, Description, Owner.Name "
        f"FROM Task WHERE {link_filter}{date_filter_task} "
        f"ORDER BY ActivityDate DESC NULLS LAST LIMIT {limit}"
    )

    classic_notes = sf.query(
        "SELECT Id, Title, Body, CreatedDate, CreatedBy.Name "
        "FROM Note "
        f"WHERE ParentId = '{record_id}'{date_filter_note} "
        f"ORDER BY CreatedDate DESC LIMIT {limit}"
    )

    content_notes = sf.query(
        "SELECT ContentDocumentId, ContentDocument.Title, "
        "ContentDocument.Description, ContentDocument.CreatedDate, "
        "ContentDocument.CreatedBy.Name "
        "FROM ContentDocumentLink "
        f"WHERE LinkedEntityId = '{record_id}' "
        "AND ContentDocument.FileType = 'SNOTE'"
    )

    meeting_notes = [
        {
            "type": "event",
            "subject": e["Subject"],
            "date": e.get("StartDateTime"),
            "description": e.get("Description"),
            "owner": e.get("Owner", {}).get("Name") if e.get("Owner") else None,
        }
        for e in events["records"]
        if e.get("Description")
    ]

    task_notes = [
        {
            "type": "task",
            "subject": t["Subject"],
            "date": t.get("ActivityDate"),
            "description": t.get("Description"),
            "owner": t.get("Owner", {}).get("Name") if t.get("Owner") else None,
        }
        for t in tasks["records"]
        if t.get("Description")
    ]

    return {
        "meeting_notes": meeting_notes,
        "task_notes": task_notes,
        "classic_notes": classic_notes["records"],
        "content_notes": content_notes["records"],
        "total": len(meeting_notes) + len(task_notes) + classic_notes["totalSize"] + content_notes["totalSize"],
    }


@mcp.tool()
def get_activities(record_id: str, include_description: bool = True) -> dict:
    """Get all tasks and events (meetings, calls, follow-ups) for a record.

    Meeting notes are stored in Event/Task Description fields — this is where
    APC notes, call logs, and meeting summaries live. Always check Description.

    Searches by WhatId (Opportunity/Account) and WhoId (Contact/Lead) to catch
    all related activities regardless of how they were linked.

    Args:
        record_id: The ID of the record (Opportunity, Account, Contact, or Lead)
        include_description: Whether to include the full Description text (default True)
    """
    sf = get_sf_client()
    desc_field = ", Description" if include_description else ""

    # Determine if this is a Contact/Lead (003/00Q prefix) or Opportunity/Account
    prefix = record_id[:3]
    is_who = prefix in ("003", "00Q")

    if is_who:
        who_filter = f"WhoId = '{record_id}'"
        tasks = sf.query(
            f"SELECT Id, Subject, ActivityDate, Status, Priority, "
            f"Owner.Name, WhatId{desc_field} "
            f"FROM Task WHERE {who_filter} "
            f"ORDER BY ActivityDate DESC NULLS LAST"
        )
        events = sf.query(
            f"SELECT Id, Subject, StartDateTime, EndDateTime, Location, "
            f"Owner.Name, WhatId{desc_field} "
            f"FROM Event WHERE {who_filter} "
            f"ORDER BY StartDateTime DESC NULLS LAST"
        )
    else:
        tasks = sf.query(
            f"SELECT Id, Subject, ActivityDate, Status, Priority, "
            f"Owner.Name, Who.Name{desc_field} "
            f"FROM Task "
            f"WHERE WhatId = '{record_id}' "
            f"ORDER BY ActivityDate DESC NULLS LAST"
        )
        events = sf.query(
            f"SELECT Id, Subject, StartDateTime, EndDateTime, Location, "
            f"Owner.Name, Who.Name{desc_field} "
            f"FROM Event "
            f"WHERE WhatId = '{record_id}' "
            f"ORDER BY StartDateTime DESC NULLS LAST"
        )

    return {
        "tasks": tasks["records"],
        "events": events["records"],
        "total_tasks": tasks["totalSize"],
        "total_events": events["totalSize"],
    }


@mcp.tool()
def get_feed(record_id: str) -> dict:
    """Get Chatter feed posts for a record.

    The Chatter feed captures comments, status updates, and tracked field
    changes posted by team members on a record. Useful for understanding
    the conversation history around a deal.

    Args:
        record_id: The ID of the record to get feed items for
    """
    sf = get_sf_client()
    # Determine the feed object from the record type prefix
    feed_items = sf.query(
        "SELECT Id, Body, Type, Title, CreatedDate, CreatedBy.Name, "
        "CommentCount, LikeCount "
        f"FROM FeedItem "
        f"WHERE ParentId = '{record_id}' "
        f"ORDER BY CreatedDate DESC "
        f"LIMIT 50"
    )
    return feed_items


@mcp.tool()
def get_field_history(object_type: str, record_id: str) -> dict:
    """Get the change history for a record's fields.

    Shows who changed what and when — useful for understanding how a deal
    has progressed (e.g. stage changes, owner changes, value updates).

    Args:
        object_type: The object type (Opportunity, Account, etc.)
        record_id: The ID of the record
    """
    sf = get_sf_client()
    history_object = f"{object_type}FieldHistory"
    id_field = f"{object_type}Id"
    try:
        result = sf.query(
            f"SELECT Id, Field, OldValue, NewValue, CreatedDate, CreatedBy.Name "
            f"FROM {history_object} "
            f"WHERE {id_field} = '{record_id}' "
            f"ORDER BY CreatedDate DESC "
            f"LIMIT 100"
        )
        return result
    except Exception as e:
        return {"error": f"Field history not available for {object_type}: {str(e)}"}


# =============================================================================
# COMPANY DEEP-DIVE TOOL
# =============================================================================
# This is the "give me everything" tool — pulls all data for a company
# in a single call so Claude can build screeners, prep for meetings, etc.
# =============================================================================

OPPORTUNITY_FIELD_MAP = {
    "fid4__c": "Account Name (legacy)",
    "fid5__c": "Address",
    "fid6__c": "Primary Contact",
    "fid8__c": "Industry",
    "fid9__c": "End market reference",
    "fid10__c": "Source type",
    "fid11__c": "Armitage partner",
    "fid12__c": "Direct Source",
    "fid14__c": "Revenue estimate ($M)",
    "fid15__c": "EBITDA estimate ($M)",
    "fid16__c": "Armitage equity cheque estimate ($M)",
    "fid17__c": "EV estimate ($M)",
    "fid24__c": "Next steps and key dates",
    "fid26__c": "Date of last EOI",
    "fid27__c": "Inflection point comments",
    "fid31__c": "Status (discussions)",
    "fid38__c": "Date of Term Sheet",
    "fid40__c": "Bolt-on for",
    "fid45__c": "Reason for kill (dead deals)",
    "fid46__c": "Cold outreach",
    "fid48__c": "Status reached for dead deals",
    "fid50__c": "Employees",
    "fid51__c": "Dead deal introduced to",
    "fid53__c": "GOWT Owner",
    "fid54__c": "Debt opportunity",
    "fid55__c": "Investment date",
    "fidled__c": "Last Event Date",
    "fidprocesscreateddate__c": "Created Date (process)",
    "fidprocessclosedate__c": "Close Date (process)",
    "fidprocessowner__c": "Owner (process)",
    "fidprocessstatus__c": "Status (process)",
}


@mcp.tool()
def get_company_overview(opportunity_id: str) -> dict:
    """Get a comprehensive overview of a company/deal from Salesforce.

    Pulls together the Opportunity record (with human-readable field names),
    related Account, Contacts, notes, activities, files, and growth summaries.
    This is the go-to tool for screener prep, meeting prep, or any deep-dive.

    Args:
        opportunity_id: The Salesforce Opportunity ID
    """
    sf = get_sf_client()

    opp = sf.Opportunity.get(opportunity_id)

    readable_opp = {}
    for key, value in opp.items():
        if key == "attributes" or value is None:
            continue
        label = OPPORTUNITY_FIELD_MAP.get(key, key)
        readable_opp[label] = value

    account = None
    if opp.get("AccountId"):
        account = sf.Account.get(opp["AccountId"])

    contacts = sf.query(
        "SELECT ContactId, Contact.Name, Contact.Email, Contact.Phone, "
        "Contact.Title, Contact.fidliurl__c, Contact.fidcompany__c, "
        "Contact.fidtitle__c, Role, IsPrimary "
        "FROM OpportunityContactRole "
        f"WHERE OpportunityId = '{opportunity_id}'"
    )

    # Meeting notes live in Event.Description and Task.Description
    tasks = sf.query(
        "SELECT Id, Subject, ActivityDate, Status, Description, Owner.Name, Who.Name "
        "FROM Task "
        f"WHERE WhatId = '{opportunity_id}' "
        "ORDER BY ActivityDate DESC NULLS LAST LIMIT 50"
    )

    events = sf.query(
        "SELECT Id, Subject, StartDateTime, EndDateTime, Description, Owner.Name, Who.Name "
        "FROM Event "
        f"WHERE WhatId = '{opportunity_id}' "
        "ORDER BY StartDateTime DESC NULLS LAST LIMIT 50"
    )

    notes = sf.query(
        "SELECT Id, Title, Body, CreatedDate "
        "FROM Note "
        f"WHERE ParentId = '{opportunity_id}' "
        "ORDER BY CreatedDate DESC"
    )

    files = sf.query(
        "SELECT ContentDocumentId, ContentDocument.Title, "
        "ContentDocument.FileType, ContentDocument.ContentSize "
        "FROM ContentDocumentLink "
        f"WHERE LinkedEntityId = '{opportunity_id}'"
    )

    growth = sf.query(
        "SELECT Id, Name, News__c, Outreach_Message__c, Potential_Actions__c, "
        "LinkedIn_URL__c, CreatedDate "
        "FROM Growth_Summary__c "
        f"WHERE Opportunity__c = '{opportunity_id}' "
        "ORDER BY CreatedDate DESC"
    )

    return {
        "opportunity": readable_opp,
        "account": {k: v for k, v in (account or {}).items() if k != "attributes" and v is not None} if account else None,
        "contacts": contacts["records"],
        "tasks": tasks["records"],
        "events": events["records"],
        "notes": notes["records"],
        "files": files["records"],
        "growth_summaries": growth["records"],
        "field_name_reference": OPPORTUNITY_FIELD_MAP,
    }


@mcp.tool()
def get_opportunity_field_map() -> dict:
    """Get the mapping of cryptic fid field names to human-readable labels.

    Many Opportunity fields have names like 'fid14__c' (legacy from SalesforceIQ
    migration). This returns the full mapping so you know what each field means.

    For example:
        fid14__c → Revenue estimate ($M)
        fid15__c → EBITDA estimate ($M)
        fid8__c  → Industry
    """
    return {
        "field_map": OPPORTUNITY_FIELD_MAP,
        "other_notable_fields": {
            "Company__c": "Company Overview (text description of the business)",
            "Growth_News__c": "Growth News (AI-generated news and signals)",
            "Growth_Actions__c": "Growth Actions (AI-generated action items)",
            "P__c": "Profile Activity (LinkedIn activity tracking)",
            "Business_Industry_Overview__c": "Business & Industry Overview (screener section)",
            "Financial_Overview__c": "Financial Overview (screener section)",
            "ABI__c": "ABI status (Yes/No)",
            "GOWT_Priority__c": "GOWT Priority (Low/Medium/High)",
            "Deal__c": "Deal Pipeline stage",
            "Company_Website__c": "Company Website URL",
            "Contact_LinkedIn__c": "Contact LinkedIn URL",
            "Origination_source__c": "Origination source",
            "Transaction_type__c": "Transaction type",
            "Intermediated_type__c": "Intermediated type",
            "Owner__c": "Owner",
            "Target_EOI_timing__c": "Target EOI timing",
            "Resurrection_Date__c": "Resurrection Date",
            "Re_outreach_review_date__c": "Re-outreach review date",
        },
    }


@mcp.tool()
def get_related_contacts(record_id: str) -> dict:
    """Get all contacts related to an Opportunity or Account.

    For Opportunities, returns contacts via OpportunityContactRole (with roles
    like 'Decision Maker', 'Business User'). For Accounts, returns contacts
    directly linked to the Account.

    Args:
        record_id: An Opportunity ID or Account ID
    """
    sf = get_sf_client()
    # Try OpportunityContactRole first
    try:
        ocr = sf.query(
            "SELECT ContactId, Contact.Name, Contact.Email, Contact.Phone, "
            "Contact.Title, Contact.fidliurl__c, Contact.fidcompany__c, "
            "Contact.fidtitle__c, Contact.fidcompanyHistory__c, "
            "Role, IsPrimary "
            "FROM OpportunityContactRole "
            f"WHERE OpportunityId = '{record_id}'"
        )
        if ocr["totalSize"] > 0:
            return {"source": "OpportunityContactRole", "contacts": ocr["records"]}
    except Exception:
        pass

    # Fall back to Account contacts
    contacts = sf.query(
        "SELECT Id, Name, Email, Phone, Title, "
        "fidliurl__c, fidcompany__c, fidtitle__c, fidcompanyHistory__c "
        "FROM Contact "
        f"WHERE AccountId = '{record_id}'"
    )
    return {"source": "Account", "contacts": contacts["records"]}


# =============================================================================
# BULK OPERATIONS
# =============================================================================
# For batch updates (e.g. updating 500 opportunities at once), Salesforce
# has a Bulk API and a Composite/Collections API. The Collections API
# (used in armitage-deployed) handles up to 200 records per call — simpler
# and fast enough for most workflows.
# =============================================================================

@mcp.tool()
def bulk_upsert(object_type: str, external_id_field: str, records: list[dict]) -> dict:
    """Upsert (insert or update) multiple records in bulk.

    "Upsert" means: if a record with the given external ID exists, update it.
    If it doesn't exist, create it. This is useful for syncing data.

    Args:
        object_type: The Salesforce object type
        external_id_field: The field to match existing records on (e.g. "External_Id__c")
        records: List of record dictionaries to upsert
    """
    sf = get_sf_client()
    sobject = getattr(sf.bulk, object_type)
    result = sobject.upsert(records, external_id_field, batch_size=200)
    logger.info(f"Bulk upserted {len(records)} {object_type} records")
    return {"results": result}


@mcp.tool()
def bulk_query(soql: str) -> list[dict]:
    """Run a bulk async query for large datasets.

    Use this instead of regular query() when you expect more than 10,000 records.
    The Bulk API runs the query asynchronously on Salesforce's side and returns
    all results without pagination limits.

    Args:
        soql: The SOQL query string
    """
    sf = get_sf_client()
    object_type = soql.strip().split("FROM")[1].strip().split()[0]
    sobject = getattr(sf.bulk, object_type)
    return sobject.query(soql)


# =============================================================================
# AUTH MIDDLEWARE
# =============================================================================
# This sits between the internet and the MCP server. Every HTTP request
# must include a valid API key as a Bearer token:
#   Authorization: Bearer <your-api-key>
#
# Valid keys are loaded from the MCP_API_KEYS environment variable
# (comma-separated). Each team member gets their own key so you can
# revoke individuals without affecting everyone.
# =============================================================================

VALID_API_KEYS = set(
    k.strip()
    for k in os.getenv("MCP_API_KEYS", "").split(",")
    if k.strip()
)


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not VALID_API_KEYS:
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"error": "Missing Authorization header"}, status_code=401)

        token = auth_header[len("Bearer "):]
        if not any(hmac.compare_digest(token, key) for key in VALID_API_KEYS):
            return JSONResponse({"error": "Invalid API key"}, status_code=401)

        return await call_next(request)


# =============================================================================
# SERVER ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    starlette_app = mcp.streamable_http_app()
    starlette_app.add_middleware(ApiKeyAuthMiddleware)

    uvicorn.run(starlette_app, host="0.0.0.0", port=8080)
