import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import requests
from simple_salesforce.exceptions import SalesforceError

from app import logger, mcp
from app.client import get_sf_client
from app.screener.build import build_docx_bytes, file_title, validate
from app.screener.downloads import FILE_MARKER, RETENTION_DAYS, download_link

SCREENER_DIR = Path(__file__).resolve().parent.parent / "screener"


def _cleanup_expired_files(sf) -> None:
    """Delete stored screener files older than RETENTION_DAYS (best effort)."""
    try:
        old = sf.query_all(
            "SELECT ContentDocumentId FROM ContentVersion "
            f"WHERE Description = '{FILE_MARKER}' AND IsLatest = true "
            f"AND CreatedDate < LAST_N_DAYS:{RETENTION_DAYS}"
        )["records"]
        for row in old:
            sf.ContentDocument.delete(row["ContentDocumentId"])
        if old:
            logger.info(f"Deleted {len(old)} expired screener file(s)")
    except (SalesforceError, requests.RequestException) as e:  # never block a build
        logger.warning(f"Screener file cleanup failed: {e}")


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
def build_screener(spec: dict) -> dict:
    """Build the final AA Investment Screener (.docx) and return a download link. Call
    get_screener_guide first; it defines the spec format and house style, and has a
    complete example spec. This is the only way to produce a screener: never generate
    the document yourself.

    The spec is validated against the house rules first. If anything is wrong, nothing
    is built and the errors are returned: fix the spec and call again. Works with full
    P&L data or teaser-only information (key_metrics, TBC fields). The download link is
    valid for 7 days; for changes, call again for a new file and link.

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

    # Stored privately in Salesforce Files (attached to no record) only so the
    # download link survives server restarts; deleted after RETENTION_DAYS.
    sf = get_sf_client()
    _cleanup_expired_files(sf)
    version_id = sf.ContentVersion.create({
        "Title": title,
        "PathOnClient": f"{title}.docx",
        "VersionData": base64.b64encode(content).decode(),
        "Description": FILE_MARKER,
    })["id"]
    doc_id = sf.query(
        f"SELECT ContentDocumentId FROM ContentVersion WHERE Id = '{version_id}'"
    )["records"][0]["ContentDocumentId"]
    url, expires = download_link(doc_id)
    logger.info(f"build_screener: {title} ({len(content)} bytes) as {doc_id}")
    return {
        "built": True,
        "title": f"{title}.docx",
        "download_url": url,
        "link_expires": datetime.fromtimestamp(expires, UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "size_bytes": len(content),
        "warnings": problems.warnings,
    }


@mcp.prompt()
def screen(company: str) -> str:
    """Build an AA Investment Screener for a company."""
    return (
        f"Build an AA Investment Screener for {company}. Call get_screener_guide first and "
        "follow it end to end: gather the attached documents, Salesforce history and public "
        "research; score the thesis; then call build_screener and give me the download link "
        "with a short summary of the recommendation."
    )
