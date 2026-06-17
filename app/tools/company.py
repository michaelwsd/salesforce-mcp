from app import mcp
from app.client import get_sf_client
from app.field_map import OPPORTUNITY_FIELD_MAP, OTHER_NOTABLE_FIELDS


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
        "other_notable_fields": OTHER_NOTABLE_FIELDS,
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

    contacts = sf.query(
        "SELECT Id, Name, Email, Phone, Title, "
        "fidliurl__c, fidcompany__c, fidtitle__c, fidcompanyHistory__c "
        "FROM Contact "
        f"WHERE AccountId = '{record_id}'"
    )
    return {"source": "Account", "contacts": contacts["records"]}


@mcp.tool()
def get_gowt_opportunities(
    priority: str | None = None,
    owner: str | None = None,
    platform_only: bool = False,
) -> dict:
    """Get opportunities in the GOWT pipeline (stage "8. Good opportunity wrong timing").

    GOWT deals are opportunities that were good but the timing wasn't right.
    They are tracked with a priority field (Ultra High, High, Medium, Low)
    to indicate re-engagement urgency.

    The "GOWT High (Platform)" report = High priority, excluding bolt-ons
    (platform_only=True).

    Args:
        priority: Optional filter — 'Ultra High', 'High', 'Medium', or 'Low'.
                  If omitted, returns all GOWT deals.
        owner: Optional GOWT Owner filter (e.g. 'APC', 'NL', 'DG', 'BO', 'MY', 'HM', 'LF').
        platform_only: If True, excludes portfolio bolt-ons (Transaction_type__c =
                       '8. Portfolio company bolt-on'). Matches the "Platform" report filter.
    """
    sf = get_sf_client()
    where = "StageName = '8. Good opportunity wrong timing'"
    if priority:
        where += f" AND GOWT_Priority__c = '{priority}'"
    if owner:
        where += f" AND fid53__c = '{owner}'"
    if platform_only:
        where += " AND Transaction_type__c != '8. Portfolio company bolt-on'"
    return sf.query_all(
        "SELECT Id, Name, StageName, GOWT_Priority__c, Transaction_type__c, "
        "fid8__c, fid14__c, fid15__c, fid17__c, fid53__c, "
        "Owner.Name, Resurrection_Date__c, Re_outreach_review_date__c, "
        "Company__c, Company_Website__c "
        "FROM Opportunity "
        f"WHERE {where} "
        "ORDER BY GOWT_Priority__c, Name"
    )
