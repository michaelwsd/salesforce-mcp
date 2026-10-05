"""Shared lookups for activities (Tasks/Events) and emails linked to a record.

Two org quirks drive this module:

1. Salesforce archives Tasks/Events older than ~1 year. Archived activities are
   invisible to the normal /query endpoint, and in this org that is ~75% of
   Tasks and ~96% of Events (most historical meeting notes). Every activity
   lookup therefore goes through /queryAll and filters out IsDeleted rows.

2. An activity can be linked to a record several ways: WhatId (Opportunity,
   Account, ...), AccountId (rolled up from child Opportunities/Contacts),
   WhoId (primary Contact/Lead), and Task/EventRelation (additional invitees).
   Each lookup alone misses records, so results are unioned and de-duplicated.
"""

WHO_PREFIXES = ("003", "00Q")  # Contact, Lead
ACCOUNT_PREFIX = "001"


def query_all_rows(sf, soql: str) -> list[dict]:
    """Run SOQL via /queryAll (includes archived + deleted), following pagination."""
    return sf.query_all(soql, include_deleted=True)["records"]


def _union(*record_lists: list[dict]) -> list[dict]:
    seen = {}
    for records in record_lists:
        for r in records:
            seen.setdefault(r["Id"], r)
    return list(seen.values())


def fetch_activities(
    sf,
    sobject: str,
    record_id: str,
    fields: str,
    date_field: str,
    since: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Return non-deleted Tasks or Events linked to record_id in any way, newest first.

    Args:
        sf: Salesforce client
        sobject: "Task" or "Event"
        record_id: Opportunity, Account, Contact, Lead, or any WhatId-able record
        fields: SOQL field list (Id is always added)
        date_field: Field used for `since` filtering and ordering
            (ActivityDate for Task, StartDateTime for Event)
        since: Optional YYYY-MM-DD lower bound on date_field
        limit: Optional cap on returned records (applied after union + sort)
    """
    select = f"SELECT Id, {fields} FROM {sobject} WHERE IsDeleted = false"
    if since:
        bound = f"{since}T00:00:00Z" if date_field.endswith("DateTime") else since
        select += f" AND {date_field} >= {bound}"

    prefix = record_id[:3]
    if prefix in WHO_PREFIXES:
        relation = "TaskRelation" if sobject == "Task" else "EventRelation"
        id_field = "TaskId" if sobject == "Task" else "EventId"
        records = _union(
            query_all_rows(sf, f"{select} AND WhoId = '{record_id}'"),
            query_all_rows(
                sf,
                f"{select} AND Id IN (SELECT {id_field} FROM {relation} "
                f"WHERE RelationId = '{record_id}')",
            ),
        )
    elif prefix == ACCOUNT_PREFIX:
        records = query_all_rows(
            sf, f"{select} AND (WhatId = '{record_id}' OR AccountId = '{record_id}')"
        )
    else:
        records = query_all_rows(sf, f"{select} AND WhatId = '{record_id}'")

    records.sort(key=lambda r: r.get(date_field) or "", reverse=True)
    return records[:limit] if limit else records


def fetch_emails(
    sf,
    record_id: str,
    fields: str,
    since: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Return EmailMessages linked to record_id, newest first.

    Opportunities/Accounts link via RelatedToId; Contacts/Leads/Users link via
    EmailMessageRelation (sender and every recipient).
    """
    select = f"SELECT Id, {fields} FROM EmailMessage WHERE IsDeleted = false"
    if since:
        select += f" AND MessageDate >= {since}T00:00:00Z"

    if record_id[:3] in WHO_PREFIXES or record_id[:3] == "005":
        where = (
            f"Id IN (SELECT EmailMessageId FROM EmailMessageRelation "
            f"WHERE RelationId = '{record_id}')"
        )
    else:
        where = f"RelatedToId = '{record_id}'"

    records = query_all_rows(sf, f"{select} AND {where} ORDER BY MessageDate DESC")
    return records[:limit] if limit else records
