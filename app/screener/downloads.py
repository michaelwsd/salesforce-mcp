"""Screener downloads: signed, expiring links to the finished .docx.

The file is held as a ContentVersion in Salesforce Files purely as storage: it is
not attached to any record, so only its owner (the integration user) can see it,
and it is deleted after RETENTION_DAYS. Users download it through
/screeners/<token> on this server; the token carries the ContentDocument ID and
an expiry, signed with HMAC so it cannot be guessed or altered. Storing the file
in Salesforce rather than on the server means links survive Render restarts and
sleeps.
"""

import base64
import hashlib
import hmac
import os
import time
from urllib.parse import quote

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from app.client import get_sf_client

FILE_MARKER = "AA screener download"   # ContentVersion.Description of stored files
RETENTION_DAYS = 7
LINK_TTL_SECONDS = RETENTION_DAYS * 24 * 3600
DOWNLOAD_PATH = "/screeners/"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _secret() -> bytes:
    """Signing key: SCREENER_LINK_SECRET if set, else derived from the Salesforce
    secret so no extra configuration is needed. Rotating either invalidates links."""
    material = (os.getenv("SCREENER_LINK_SECRET") or os.getenv("CONSUMER_SECRET")
                or os.getenv("SALESFORCE_PASSWORD"))
    if not material:
        raise RuntimeError("No secret available to sign screener download links")
    return hashlib.sha256(f"screener-download-link:{material}".encode()).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(document_id: str, expires: int) -> str:
    payload = f"{document_id}.{expires}".encode()
    mac = hmac.new(_secret(), payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(mac)}"


def verify(token: str) -> str | None:
    """Return the ContentDocument ID if the token is authentic and unexpired."""
    try:
        payload_b64, mac_b64 = token.split(".")
        payload = _unb64(payload_b64)
        expected = hmac.new(_secret(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(mac_b64)):
            return None
        document_id, expires = payload.decode().split(".")
        if int(expires) < time.time():
            return None
        return document_id
    except (ValueError, UnicodeDecodeError):
        return None


def public_base_url() -> str:
    """This server's public URL (Render sets RENDER_EXTERNAL_URL)."""
    url = os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL")
    return (url or f"http://localhost:{os.getenv('PORT', '8080')}").rstrip("/")


def download_link(document_id: str) -> tuple[str, int]:
    expires = int(time.time()) + LINK_TTL_SECONDS
    return f"{public_base_url()}{DOWNLOAD_PATH}{sign(document_id, expires)}", expires


def _message(title: str, text: str, status: int) -> HTMLResponse:
    html = (
        "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
        f"<title>{title}</title><body style='font-family:Calibri,Arial,sans-serif;"
        f"max-width:560px;margin:15vh auto;padding:0 16px;color:#0E2841'><h2>{title}</h2>"
        f"<p>{text}</p></body>"
    )
    return HTMLResponse(html, status_code=status)


def _fetch(document_id: str) -> tuple[str, bytes] | None:
    sf = get_sf_client()
    rows = sf.query(
        "SELECT Title, VersionData FROM ContentVersion "
        f"WHERE ContentDocumentId = '{document_id}' AND IsLatest = true"
    )["records"]
    if not rows:
        return None
    host = sf.base_url.split("/services/")[0]
    resp = sf.session.get(f"{host}{rows[0]['VersionData']}",
                          headers={"Authorization": f"Bearer {sf.session_id}"}, timeout=120)
    resp.raise_for_status()
    return rows[0]["Title"], resp.content


async def download_screener(request: Request) -> Response:
    document_id = verify(request.path_params["token"])
    if not document_id:
        return _message("Link expired", "This screener link is invalid or has expired "
                        f"(links last {RETENTION_DAYS} days). Ask Claude to rebuild it.", 404)
    found = await run_in_threadpool(_fetch, document_id)
    if not found:
        return _message("Screener not found", "This screener file no longer exists. "
                        f"Files are kept for {RETENTION_DAYS} days; ask Claude to rebuild it.", 404)
    title, content = found
    filename = f"{title}.docx"
    # HTTP headers are latin-1: plain ASCII fallback plus the RFC 5987 UTF-8 form.
    ascii_name = filename.encode("ascii", "replace").decode().replace("?", "_").replace('"', "")
    return Response(content, media_type=DOCX_MIME, headers={
        "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}",
        "Cache-Control": "no-store",
    })
