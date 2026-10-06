import base64
import json
from datetime import UTC, datetime
from pathlib import Path

from app import logger, mcp
from app.client import get_sf_client
from app.screener.build import build_docx_bytes, file_title, validate

SCREENER_DIR = Path(__file__).resolve().parent.parent / "screener"

# Team conventions for a newly logged deal (matches recent Opportunities).
NEW_DEAL_STAGE = "4. Medium"
NEW_DEAL_CLOSE_DATE = "2049-01-01"


def _soql_str(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _host(sf) -> str:
    return sf.base_url.split("/services/")[0]


def _picklist(sf, field: str) -> list[str]:
    for f in sf.Opportunity.describe()["fields"]:
        if f["name"] == field:
            return [p["value"] for p in f["picklistValues"] if p["active"]]
    return []


@mcp.tool()
def get_screener_guide() -> str:
    """Get the AA Investment Screener guide. CALL THIS FIRST whenever the user asks to
    screen a company, build/run/update an investment screener or screening memo, or
    assess an IM, teaser or CIM ("screen Acme", "should we look at this deal?").

    Returns the full workflow (research, Salesforce checks, scoring), the AA house style,
    the spec format for build_screener, and a complete example spec.
    """
    guide = (SCREENER_DIR / "guide.md").read_text(encoding="utf-8")
    example = (SCREENER_DIR / "example_spec.json").read_text(encoding="utf-8")
    return f"{guide}\n\n---\n\n## Complete example spec (fictional company)\n\n```json\n{example}```\n"


@mcp.tool()
def create_deal(
    company_name: str,
    industry: str,
    location: str,
    source_type: str,
    discussion_status: str = "2. Initial discussion",
) -> dict:
    """Log a new company in Salesforce (Account + Opportunity) the way the team does,
    so a screener can be attached to it. Only use when search finds no existing
    Opportunity for the company. If one already exists it is returned, not duplicated.

    Args:
        company_name: Company name (used for both the Account and the Opportunity)
        industry: Opportunity Industry picklist value, e.g. "Healthcare", "IT - Software",
            "Services - professional, scientific, and technical", "Manufacturing"
        location: Head office city, e.g. "Sydney", "Melbourne", "Auckland"
        source_type: "Direct", "Intermediated (sell side)" or "Direct (bolt-on)"
        discussion_status: "1. Active discussion", "2. Initial discussion" (default),
            "3. Pre conversation" or "4. Slow burn"
    """
    sf = get_sf_client()
    name = company_name.strip()

    for arg, field, value in (("industry", "fid8__c", industry), ("source_type", "fid10__c", source_type),
                              ("discussion_status", "fid31__c", discussion_status)):
        allowed = _picklist(sf, field)
        if value not in allowed:
            return {"error": f"'{value}' is not a valid {arg}. Allowed: {allowed}"}

    existing = sf.query(
        f"SELECT Id, Name, StageName, AccountId FROM Opportunity WHERE Name = '{_soql_str(name)}' LIMIT 1"
    )["records"]
    if existing:
        opp = existing[0]
        return {
            "created": False,
            "opportunity_id": opp["Id"],
            "account_id": opp["AccountId"],
            "note": f"Opportunity '{opp['Name']}' already exists (stage {opp['StageName']}); not duplicated.",
        }

    accounts = sf.query(f"SELECT Id FROM Account WHERE Name = '{_soql_str(name)}' LIMIT 1")["records"]
    account_id = accounts[0]["Id"] if accounts else sf.Account.create({"Name": name})["id"]

    opp_id = sf.Opportunity.create({
        "Name": name,
        "AccountId": account_id,
        "StageName": NEW_DEAL_STAGE,
        "CloseDate": NEW_DEAL_CLOSE_DATE,
        "fid8__c": industry,
        "fid5__c": location,
        "fid10__c": source_type,
        "fid31__c": discussion_status,
        "fidprocesscreateddate__c": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })["id"]
    logger.info(f"create_deal: created Opportunity {opp_id} for '{name}'")
    return {
        "created": True,
        "opportunity_id": opp_id,
        "account_id": account_id,
        "account_created": not accounts,
        "opportunity_url": f"{_host(sf)}/lightning/r/Opportunity/{opp_id}/view",
    }


@mcp.tool()
def build_screener(spec: dict, opportunity_id: str) -> dict:
    """Build an AA Investment Screener (.docx) and attach it to the deal's Opportunity
    in Salesforce. Call get_screener_guide first; it defines the spec format and house
    style, and has a complete example spec.

    The spec is validated against the house rules first. If anything is wrong, nothing
    is built and the errors are returned: fix the spec and call again. On success the
    file is uploaded to Salesforce Files as "Screener_Project X" and linked to the
    Opportunity; building again for the same deal uploads a new version of that file.

    Args:
        spec: The screener spec (see get_screener_guide)
        opportunity_id: The Opportunity to attach the screener to (from search, or
            create_deal if the company is not in Salesforce yet)
    """
    if isinstance(spec, str):  # some clients send the object as a JSON string
        spec = json.loads(spec)

    problems = validate(spec)
    if problems.errors:
        return {"built": False, "errors": problems.errors, "warnings": problems.warnings}

    sf = get_sf_client()
    opp = sf.query(f"SELECT Id, Name FROM Opportunity WHERE Id = '{_soql_str(opportunity_id)}'")["records"]
    if not opp:
        return {"built": False, "errors": [f"No Opportunity with Id {opportunity_id}"]}

    content = build_docx_bytes(spec)
    title = file_title(spec)

    version = {
        "Title": title,
        "PathOnClient": f"{title}.docx",
        "VersionData": base64.b64encode(content).decode(),
    }
    existing = sf.query(
        "SELECT ContentDocumentId FROM ContentDocumentLink "
        f"WHERE LinkedEntityId = '{opp[0]['Id']}' AND ContentDocument.Title = '{_soql_str(title)}' LIMIT 1"
    )["records"]
    if existing:
        version["ContentDocumentId"] = existing[0]["ContentDocumentId"]
        version["ReasonForChange"] = "Rebuilt by build_screener"
    else:
        version["FirstPublishLocationId"] = opp[0]["Id"]
    version_id = sf.ContentVersion.create(version)["id"]

    saved = sf.query(
        f"SELECT ContentDocumentId, VersionNumber FROM ContentVersion WHERE Id = '{version_id}'"
    )["records"][0]
    doc_id = saved["ContentDocumentId"]
    host = _host(sf)
    logger.info(f"build_screener: {title} v{saved['VersionNumber']} ({len(content)} bytes) on {opp[0]['Name']}")
    return {
        "built": True,
        "title": f"{title}.docx",
        "version": int(saved["VersionNumber"]),
        "size_bytes": len(content),
        "opportunity": opp[0]["Name"],
        "file_url": f"{host}/lightning/r/ContentDocument/{doc_id}/view",
        "opportunity_url": f"{host}/lightning/r/Opportunity/{opp[0]['Id']}/view",
        "content_document_id": doc_id,
        "warnings": problems.warnings,
    }


@mcp.prompt()
def screen(company: str) -> str:
    """Build an AA Investment Screener for a company."""
    return (
        f"Build an AA Investment Screener for {company}. Call get_screener_guide first and "
        "follow it end to end: gather the attached documents, Salesforce history and public "
        "research; score the thesis; then call build_screener and give me the Salesforce link "
        "with a short summary of the recommendation."
    )
