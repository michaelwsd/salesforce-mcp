import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import requests
from simple_salesforce.exceptions import SalesforceError

from app import logger, mcp
from app.client import get_sf_client
from app.screener.build import build_docx_bytes, file_title, validate
from app.screener.drafts import APPROVED_MARKER, DRAFT_MARKER, DRAFT_RETENTION_DAYS, download_link

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
    so an approved screener can be attached to it. For screeners, call this only after
    the user approves the draft, and only when search finds no existing Opportunity for
    the company. If one already exists it is returned, not duplicated.

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


def _cleanup_old_drafts(sf) -> None:
    """Delete drafts never approved within DRAFT_RETENTION_DAYS (best effort)."""
    try:
        old = sf.query_all(
            "SELECT ContentDocumentId FROM ContentVersion "
            f"WHERE Description = '{DRAFT_MARKER}' AND IsLatest = true "
            f"AND CreatedDate < LAST_N_DAYS:{DRAFT_RETENTION_DAYS}"
        )["records"]
        for row in old:
            sf.ContentDocument.delete(row["ContentDocumentId"])
        if old:
            logger.info(f"Deleted {len(old)} unapproved screener draft(s)")
    except (SalesforceError, requests.RequestException) as e:  # never block a build
        logger.warning(f"Screener draft cleanup failed: {e}")


@mcp.tool()
def build_screener(spec: dict) -> dict:
    """Build an AA Investment Screener (.docx) as a DRAFT for human review. Call
    get_screener_guide first; it defines the spec format and house style, and has a
    complete example spec.

    The spec is validated against the house rules first. If anything is wrong, nothing
    is built and the errors are returned: fix the spec and call again. On success the
    draft is saved privately in Salesforce Files (not attached to any deal) and a
    download link valid for 24 hours is returned. Give the user the link and wait for
    their explicit approval of this draft before calling approve_screener. For
    revisions, call build_screener again; each build is a new draft with a new link.

    Args:
        spec: The screener spec (see get_screener_guide)
    """
    if isinstance(spec, str):  # some clients send the object as a JSON string
        spec = json.loads(spec)

    problems = validate(spec)
    if problems.errors:
        return {"built": False, "errors": problems.errors, "warnings": problems.warnings}

    content = build_docx_bytes(spec)
    title = file_title(spec)

    sf = get_sf_client()
    _cleanup_old_drafts(sf)
    version_id = sf.ContentVersion.create({
        "Title": title,
        "PathOnClient": f"{title}.docx",
        "VersionData": base64.b64encode(content).decode(),
        "Description": DRAFT_MARKER,
    })["id"]
    doc_id = sf.query(
        f"SELECT ContentDocumentId FROM ContentVersion WHERE Id = '{version_id}'"
    )["records"][0]["ContentDocumentId"]
    url, expires = download_link(doc_id)
    logger.info(f"build_screener: draft {title} ({len(content)} bytes) as {doc_id}")
    return {
        "built": True,
        "status": "draft - awaiting the user's approval",
        "title": f"{title}.docx",
        "draft_id": doc_id,
        "download_url": url,
        "link_expires": datetime.fromtimestamp(expires, UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "size_bytes": len(content),
        "warnings": problems.warnings,
    }


@mcp.tool()
def approve_screener(draft_id: str, opportunity_id: str) -> dict:
    """Attach an approved screener draft to the deal's Opportunity in Salesforce.

    ONLY call this after the user has reviewed the draft and explicitly approved it
    (e.g. "looks good, upload it"). Never call it in the same turn as build_screener,
    and never on your own judgement. The exact reviewed file is attached, not rebuilt.
    If the Opportunity already has a screener with the same title, the draft becomes a
    new version of that file instead of a duplicate.

    Args:
        draft_id: The draft_id returned by build_screener for the approved draft
        opportunity_id: The deal's Opportunity (from search, or create_deal if the
            company is not in Salesforce yet)
    """
    sf = get_sf_client()
    draft = sf.query(
        "SELECT Id, Title, Description, VersionData FROM ContentVersion "
        f"WHERE ContentDocumentId = '{_soql_str(draft_id)}' AND IsLatest = true"
    )["records"]
    if not draft:
        return {"approved": False, "error": f"No draft {draft_id}; it may have expired (7 days). Rebuild it."}
    if draft[0]["Description"] != DRAFT_MARKER:
        return {"approved": False, "error": f"{draft_id} is not a pending screener draft (already approved?)."}
    opp = sf.query(f"SELECT Id, Name FROM Opportunity WHERE Id = '{_soql_str(opportunity_id)}'")["records"]
    if not opp:
        return {"approved": False, "error": f"No Opportunity with Id {opportunity_id}"}

    title = draft[0]["Title"]
    existing = sf.query(
        "SELECT ContentDocumentId FROM ContentDocumentLink "
        f"WHERE LinkedEntityId = '{opp[0]['Id']}' AND ContentDocument.Title = '{_soql_str(title)}' "
        f"AND ContentDocumentId != '{draft_id}' LIMIT 1"
    )["records"]
    if existing:
        # Copy the reviewed bytes in as a new version of the deal's screener file.
        host = _host(sf)
        resp = sf.session.get(f"{host}{draft[0]['VersionData']}",
                              headers={"Authorization": f"Bearer {sf.session_id}"}, timeout=120)
        resp.raise_for_status()
        doc_id = existing[0]["ContentDocumentId"]
        sf.ContentVersion.create({
            "ContentDocumentId": doc_id,
            "Title": title,
            "PathOnClient": f"{title}.docx",
            "VersionData": base64.b64encode(resp.content).decode(),
            "Description": APPROVED_MARKER,
            "ReasonForChange": "Approved screener draft",
        })
        sf.ContentDocument.delete(draft_id)
    else:
        doc_id = draft_id
        sf.ContentDocumentLink.create({
            "ContentDocumentId": doc_id,
            "LinkedEntityId": opp[0]["Id"],
            "ShareType": "I",
            "Visibility": "AllUsers",
        })
        sf.ContentVersion.update(draft[0]["Id"], {"Description": APPROVED_MARKER})

    version = sf.query(
        f"SELECT VersionNumber FROM ContentVersion WHERE ContentDocumentId = '{doc_id}' AND IsLatest = true"
    )["records"][0]["VersionNumber"]
    host = _host(sf)
    logger.info(f"approve_screener: {title} v{version} on {opp[0]['Name']}")
    return {
        "approved": True,
        "title": f"{title}.docx",
        "version": int(version),
        "opportunity": opp[0]["Name"],
        "file_url": f"{host}/lightning/r/ContentDocument/{doc_id}/view",
        "opportunity_url": f"{host}/lightning/r/Opportunity/{opp[0]['Id']}/view",
    }


@mcp.prompt()
def screen(company: str) -> str:
    """Build an AA Investment Screener for a company."""
    return (
        f"Build an AA Investment Screener for {company}. Call get_screener_guide first and "
        "follow it end to end: gather the attached documents, Salesforce history and public "
        "research; score the thesis; then call build_screener and give me the draft download "
        "link with a short summary of the recommendation. Wait for my approval before "
        "attaching it to Salesforce."
    )
