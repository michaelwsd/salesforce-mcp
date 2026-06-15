from app import mcp
from app.client import get_sf_client


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
