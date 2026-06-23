from xml.sax.saxutils import escape
import re
import requests

from app import mcp, logger
from app.client import get_sf_client

# Salesforce allows up to 10 SingleEmailMessages per sendEmail() SOAP call.
MAX_MESSAGES_PER_CALL = 10


def _soap_endpoint(sf) -> str:
    """Build the partner SOAP endpoint, reusing the client's API version."""
    host = sf.base_url.split("/services/")[0]
    version = sf.base_url.rstrip("/").split("/")[-1].lstrip("v")  # e.g. "59.0"
    return f"{host}/services/Soap/u/{version}"


def _build_message(
    subject: str,
    body: str,
    html_body: bool,
    contact_id: str | None,
    to_address: str | None,
    entity_attachment_ids: list[str],
    file_attachments: list[dict],
    save_as_activity: bool,
    org_wide_email_address_id: str | None,
) -> str:
    """Render one <messages> SingleEmailMessage element."""
    parts = [
        f"<urn:subject>{escape(subject)}</urn:subject>",
        f"<urn:{'htmlBody' if html_body else 'plainTextBody'}>{escape(body)}"
        f"</urn:{'htmlBody' if html_body else 'plainTextBody'}>",
        f"<urn:saveAsActivity>{str(save_as_activity).lower()}</urn:saveAsActivity>",
        "<urn:useSignature>false</urn:useSignature>",
    ]
    if contact_id:
        parts.append(f"<urn:targetObjectId>{contact_id}</urn:targetObjectId>")
    if to_address:
        parts.append(f"<urn:toAddresses>{escape(to_address)}</urn:toAddresses>")
    if org_wide_email_address_id:
        parts.append(
            f"<urn:orgWideEmailAddressId>{org_wide_email_address_id}"
            "</urn:orgWideEmailAddressId>"
        )
    for vid in entity_attachment_ids:
        parts.append(f"<urn:entityAttachments>{vid}</urn:entityAttachments>")
    for fa in file_attachments:
        parts.append(
            "<urn:fileAttachments>"
            f"<urn:fileName>{escape(fa['filename'])}</urn:fileName>"
            f"<urn:contentType>{escape(fa.get('content_type', 'application/octet-stream'))}</urn:contentType>"
            f"<urn:body>{fa['base64_body']}</urn:body>"
            "</urn:fileAttachments>"
        )
    return '<urn:messages xsi:type="urn:SingleEmailMessage">' + "".join(parts) + "</urn:messages>"


def _send_batch(sf, messages_xml: list[str]) -> list[dict]:
    """POST one sendEmail call (<=10 messages) and parse per-message results."""
    endpoint = _soap_endpoint(sf)
    envelope = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:urn="urn:partner.soap.sforce.com" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<soapenv:Header><urn:SessionHeader><urn:sessionId>{sf.session_id}"
        "</urn:sessionId></urn:SessionHeader></soapenv:Header>"
        "<soapenv:Body><urn:sendEmail>"
        + "".join(messages_xml)
        + "</urn:sendEmail></soapenv:Body></soapenv:Envelope>"
    )
    resp = requests.post(
        endpoint,
        data=envelope.encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=UTF-8", "SOAPAction": "sendEmail"},
    )

    # A SOAP fault (auth/schema error) applies to the whole batch.
    fault = re.search(r"<faultstring>(.*?)</faultstring>", resp.text, re.DOTALL)
    if fault:
        return [{"success": False, "error": fault.group(1).strip()}] * len(messages_xml)

    # One <result> block per message, in order.
    results = []
    for block in re.findall(r"<result[^>]*>(.*?)</result>", resp.text, re.DOTALL):
        success = "<success>true</success>" in block
        entry = {"success": success}
        if not success:
            msg = re.search(r"<message>(.*?)</message>", block, re.DOTALL)
            code = re.search(r"<statusCode>(.*?)</statusCode>", block, re.DOTALL)
            entry["error"] = msg.group(1).strip() if msg else "unknown error"
            if code:
                entry["status_code"] = code.group(1).strip()
        results.append(entry)

    # Defensive: if parsing found nothing, surface the raw response.
    if not results:
        return [{"success": False, "error": resp.text[:500]}] * len(messages_xml)
    return results


@mcp.tool()
def upload_email_attachment(filename: str, base64_body: str) -> dict:
    """Upload a file once as a ContentVersion so it can be reused as an email attachment.

    This is the efficient way to attach a file to a bulk email: upload it a single
    time here, then pass the returned content_version_id to bulk_email's
    attachment_content_version_ids. Salesforce references the stored file for every
    recipient instead of re-encoding the bytes per message.

    Args:
        filename: The attachment file name (e.g. "Armitage_Teaser.pdf")
        base64_body: The file content, base64-encoded
    """
    sf = get_sf_client()
    result = sf.ContentVersion.create({
        "Title": filename,
        "PathOnClient": filename,
        "VersionData": base64_body,
    })
    version_id = result["id"]
    logger.info(f"Uploaded email attachment '{filename}' as ContentVersion {version_id}")
    return {"content_version_id": version_id, "filename": filename}


@mcp.tool()
def bulk_email(
    subject: str,
    body: str,
    contact_ids: list[str] | None = None,
    to_addresses: list[str] | None = None,
    attachment_content_version_ids: list[str] | None = None,
    file_attachments: list[dict] | None = None,
    html_body: bool = False,
    org_wide_email_address_id: str | None = None,
    save_as_activity: bool = False,
    skip_opted_out: bool = True,
) -> dict:
    """Send a bulk outreach email (optionally with attachments) to many recipients.

    Each recipient gets their own individual email (no shared To: line), batched
    10-per-call via the Salesforce sendEmail SOAP API. Daily cap is 5,000 emails.

    Recipients can be specified two ways (you may combine them):
    - contact_ids: Salesforce Contact/Lead IDs. PREFERRED for outreach — sends via
      targetObjectId so Salesforce honors email opt-out, merges fields, and (if
      save_as_activity=True) logs the send on the record.
    - to_addresses: raw email addresses. Use for non-Salesforce recipients. These
      bypass opt-out checks, so use deliberately.

    Attachments (apply to every recipient):
    - attachment_content_version_ids: PREFERRED. IDs from upload_email_attachment —
      uploaded once, referenced for all recipients.
    - file_attachments: inline list of {filename, content_type, base64_body}. Re-sent
      per message, so only use for small one-off files.

    Args:
        subject: Email subject line
        body: Email body. Plain text unless html_body=True.
        contact_ids: Salesforce Contact/Lead IDs to email (uses targetObjectId)
        to_addresses: Raw email addresses to email (uses toAddresses)
        attachment_content_version_ids: ContentVersion IDs to attach to every email
        file_attachments: Inline attachments [{filename, content_type, base64_body}]
        html_body: Treat body as HTML instead of plain text
        org_wide_email_address_id: Optional verified Org-Wide Email Address ID to send
            "from" (instead of the running user's address)
        save_as_activity: Log the email as an activity (only valid with contact_ids)
        skip_opted_out: When True (default), filter out contacts with
            HasOptedOutOfEmail=True before sending and report them as skipped
    """
    sf = get_sf_client()
    contact_ids = list(contact_ids or [])
    to_addresses = list(to_addresses or [])
    entity_ids = list(attachment_content_version_ids or [])
    file_atts = list(file_attachments or [])

    if not contact_ids and not to_addresses:
        return {"error": "Provide at least one of contact_ids or to_addresses."}

    skipped_opted_out: list[str] = []
    if contact_ids and skip_opted_out:
        # Only Contact/Lead carry HasOptedOutOfEmail; query and drop opted-out IDs.
        quoted = ", ".join(f"'{cid}'" for cid in contact_ids)
        opted_out = set()
        for obj in ("Contact", "Lead"):
            try:
                rows = sf.query_all(
                    f"SELECT Id FROM {obj} WHERE Id IN ({quoted}) "
                    "AND HasOptedOutOfEmail = true"
                )
                opted_out.update(r["Id"] for r in rows["records"])
            except Exception:
                # Object may not be queryable with these IDs; ignore.
                pass
        if opted_out:
            skipped_opted_out = [c for c in contact_ids if c in opted_out]
            contact_ids = [c for c in contact_ids if c not in opted_out]

    # Build one message per recipient (individual emails).
    messages = [
        _build_message(subject, body, html_body, cid, None, entity_ids, file_atts,
                       save_as_activity, org_wide_email_address_id)
        for cid in contact_ids
    ] + [
        _build_message(subject, body, html_body, None, addr, entity_ids, file_atts,
                       save_as_activity, org_wide_email_address_id)
        for addr in to_addresses
    ]
    # Recipient label aligned with message order, for per-recipient reporting.
    labels = contact_ids + to_addresses

    if not messages:
        return {
            "sent": 0,
            "failed": 0,
            "skipped_opted_out": skipped_opted_out,
            "note": "All recipients were opted out; nothing sent.",
        }

    sent = 0
    failures: list[dict] = []
    for i in range(0, len(messages), MAX_MESSAGES_PER_CALL):
        batch = messages[i:i + MAX_MESSAGES_PER_CALL]
        batch_labels = labels[i:i + MAX_MESSAGES_PER_CALL]
        for label, result in zip(batch_labels, _send_batch(sf, batch)):
            if result.get("success"):
                sent += 1
            else:
                failures.append({"recipient": label, **{k: v for k, v in result.items() if k != "success"}})

    logger.info(
        f"bulk_email: {sent} sent, {len(failures)} failed, "
        f"{len(skipped_opted_out)} opted-out skipped"
    )
    return {
        "sent": sent,
        "failed": len(failures),
        "failures": failures,
        "skipped_opted_out": skipped_opted_out,
    }
