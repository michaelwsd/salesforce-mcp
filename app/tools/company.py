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
