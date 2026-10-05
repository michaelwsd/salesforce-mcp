from app import mcp
from app.activities import fetch_activities, fetch_emails
from app.client import get_sf_client


def _owner(record: dict) -> str | None:
    return (record.get("Owner") or {}).get("Name")


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

    Includes archived activities (older than ~1 year), which hold most of the
    historical meeting notes. For Accounts, also includes activities logged on
    the Account's Opportunities and Contacts. For Contacts/Leads, includes
    activities where they are any invitee, not just the primary contact.

    Always call this tool when asked about notes for a company or deal.

    Args:
        record_id: The ID of the record (Opportunity, Account, Contact, or Lead)
        since: Optional date filter — only return notes from this date onwards.
               Format: YYYY-MM-DD (e.g. "2026-01-01"). Use this for "recent notes",
               "notes from last month", etc.
        limit: Maximum number of notes to return per category (default 20)
    """
    sf = get_sf_client()

    # Description is a long text area and can't be filtered in SOQL, so fetch
    # all linked activities and keep only those with notes before limiting.
    events = fetch_activities(
        sf, "Event", record_id, "Subject, StartDateTime, Description, Owner.Name",
        "StartDateTime", since=since,
    )
    tasks = fetch_activities(
        sf, "Task", record_id, "Subject, ActivityDate, Description, Owner.Name",
        "ActivityDate", since=since,
    )

    date_filter_note = f" AND CreatedDate >= {since}T00:00:00Z" if since else ""
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
        "AND ContentDocument.FileType = 'SNOTE' "
        f"LIMIT {limit}"
    )

    meeting_notes = [
        {
            "type": "event",
            "id": e["Id"],
            "subject": e["Subject"],
            "date": e.get("StartDateTime"),
            "description": e["Description"],
            "owner": _owner(e),
        }
        for e in events
        if e.get("Description")
    ]

    task_notes = [
        {
            "type": "task",
            "id": t["Id"],
            "subject": t["Subject"],
            "date": t.get("ActivityDate"),
            "description": t["Description"],
            "owner": _owner(t),
        }
        for t in tasks
        if t.get("Description")
    ]

    return {
        "meeting_notes": meeting_notes[:limit],
        "task_notes": task_notes[:limit],
        "classic_notes": classic_notes["records"],
        "content_notes": content_notes["records"],
        "total_available": {
            "meeting_notes": len(meeting_notes),
            "task_notes": len(task_notes),
            "classic_notes": classic_notes["totalSize"],
            "content_notes": content_notes["totalSize"],
        },
    }


@mcp.tool()
def get_activities(
    record_id: str,
    include_description: bool = True,
    since: str | None = None,
    limit: int = 200,
) -> dict:
    """Get all tasks and events (meetings, calls, follow-ups) for a record.

    Meeting notes are stored in Event/Task Description fields — this is where
    APC notes, call logs, and meeting summaries live. Always check Description.

    Includes archived activities (older than ~1 year). Finds activities linked
    by WhatId (Opportunity/Account), AccountId (rolled up from an Account's
    Opportunities and Contacts), WhoId and Task/EventRelation (Contact/Lead as
    primary contact or any invitee).

    Args:
        record_id: The ID of the record (Opportunity, Account, Contact, or Lead)
        include_description: Whether to include the full Description text (default True)
        since: Optional YYYY-MM-DD — only activities on or after this date
        limit: Maximum tasks and maximum events to return (default 200 each)
    """
    sf = get_sf_client()
    desc_field = ", Description" if include_description else ""

    tasks = fetch_activities(
        sf, "Task", record_id,
        f"Subject, ActivityDate, Status, Priority, TaskSubtype, Owner.Name, "
        f"Who.Name, What.Name, IsArchived{desc_field}",
        "ActivityDate", since=since,
    )
    events = fetch_activities(
        sf, "Event", record_id,
        f"Subject, StartDateTime, EndDateTime, Location, Owner.Name, "
        f"Who.Name, What.Name, IsArchived{desc_field}",
        "StartDateTime", since=since,
    )

    return {
        "tasks": tasks[:limit],
        "events": events[:limit],
        "total_tasks": len(tasks),
        "total_events": len(events),
    }


@mcp.tool()
def get_emails(
    record_id: str,
    since: str | None = None,
    limit: int = 50,
    include_body: bool = True,
    max_body_chars: int = 5000,
) -> dict:
    """Get emails (EmailMessage) logged against a record.

    Emails are a large share of the org's history (~90k messages): intro emails,
    advisor correspondence, deal teasers, and replies. For Opportunities and
    Accounts, matches emails whose Related To is the record. For Contacts,
    Leads, and Users, matches emails where they are the sender or any recipient.

    Args:
        record_id: Opportunity, Account, Contact, Lead, or User ID
        since: Optional YYYY-MM-DD — only emails on or after this date
        limit: Maximum emails to return, newest first (default 50)
        include_body: Include the plain-text body (default True)
        max_body_chars: Truncate each body to this many characters (default 5000)
    """
    sf = get_sf_client()
    body = ", TextBody" if include_body else ""
    emails = fetch_emails(
        sf, record_id,
        "Subject, MessageDate, FromName, FromAddress, ToAddress, CcAddress, "
        f"Incoming, HasAttachment, RelatedToId, ActivityId{body}",
        since=since,
    )
    returned = emails[:limit]
    if include_body:
        for e in returned:
            text = e.get("TextBody") or ""
            if len(text) > max_body_chars:
                e["TextBody"] = text[:max_body_chars] + f"\n...[truncated, {len(text)} chars total]"
    return {"emails": returned, "total": len(emails), "returned": len(returned)}


@mcp.tool()
def get_feed(record_id: str, limit: int = 50) -> dict:
    """Get Chatter feed posts (with their comments) for a record.

    The Chatter feed captures comments, status updates, and tracked field
    changes posted by team members on a record. Useful for understanding
    the conversation history around a deal.

    Args:
        record_id: The ID of the record to get feed items for
        limit: Maximum feed posts to return, newest first (default 50)
    """
    sf = get_sf_client()
    return sf.query(
        "SELECT Id, Body, Type, Title, LinkUrl, CreatedDate, CreatedBy.Name, "
        "CommentCount, LikeCount, "
        "(SELECT CommentBody, CreatedDate, CreatedBy.Name FROM FeedComments "
        "ORDER BY CreatedDate) "
        "FROM FeedItem "
        f"WHERE ParentId = '{record_id}' "
        "ORDER BY CreatedDate DESC "
        f"LIMIT {limit}"
    )


def _history_source(object_type: str) -> tuple[str, str]:
    """Return (history object, parent id field) for an object's field history.

    Standard objects use <Object>History/<Object>Id, except Opportunity which
    uses OpportunityFieldHistory. Custom objects use <Name>__History/ParentId.
    """
    if object_type == "Opportunity":
        return "OpportunityFieldHistory", "OpportunityId"
    if object_type.endswith("__c"):
        return f"{object_type[:-3]}__History", "ParentId"
    return f"{object_type}History", f"{object_type}Id"


@mcp.tool()
def get_field_history(object_type: str, record_id: str, limit: int = 200) -> dict:
    """Get the change history for a record's fields.

    Shows who changed what and when — useful for understanding how a deal
    has progressed (e.g. stage changes, owner changes, value updates).
    Only fields with history tracking enabled are recorded.

    Args:
        object_type: The object type (Opportunity, Account, Contact, Lead, Exit__c, ...)
        record_id: The ID of the record
        limit: Maximum changes to return, newest first (default 200)
    """
    sf = get_sf_client()
    history_object, id_field = _history_source(object_type)
    try:
        return sf.query(
            "SELECT Id, Field, OldValue, NewValue, CreatedDate, CreatedBy.Name "
            f"FROM {history_object} "
            f"WHERE {id_field} = '{record_id}' "
            "ORDER BY CreatedDate DESC "
            f"LIMIT {limit}"
        )
    except Exception as e:
        return {"error": f"Field history not available for {object_type}: {str(e)}"}
