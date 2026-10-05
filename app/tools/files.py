import base64

from app import mcp, logger
from app.client import get_sf_client

MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024


@mcp.tool()
def list_files(record_id: str) -> dict:
    """List all files (ContentDocuments) linked to a Salesforce record.

    Returns the file title, type, and size for each attached document.
    Use this to find CIMs, IMs, screeners, or other docs linked to
    an Opportunity or Account.

    Args:
        record_id: The ID of the record to list files for (e.g. an Opportunity ID)
    """
    sf = get_sf_client()
    return sf.query(
        "SELECT ContentDocumentId, ContentDocument.Title, "
        "ContentDocument.FileType, ContentDocument.ContentSize "
        "FROM ContentDocumentLink "
        f"WHERE LinkedEntityId = '{record_id}'"
    )


@mcp.tool()
def get_file(document_id: str) -> dict:
    """Get file metadata and download URL for a ContentDocument.

    Returns the file's latest version info including title, type, and size.
    The download_path requires a Salesforce session; use download_file to get
    the file content itself.

    Args:
        document_id: The ContentDocument ID (starts with 069)
    """
    sf = get_sf_client()
    version = sf.query(
        "SELECT Id, Title, FileType, ContentSize, VersionData "
        "FROM ContentVersion "
        f"WHERE ContentDocumentId = '{document_id}' "
        "AND IsLatest = true"
    )
    if not version["records"]:
        return {"error": f"No version found for document {document_id}"}
    record = version["records"][0]
    host = sf.base_url.split("/services/")[0]
    return {
        "id": record["Id"],
        "title": record["Title"],
        "file_type": record["FileType"],
        "size": record["ContentSize"],
        "download_path": f"{host}{record['VersionData']}",
    }


@mcp.tool()
def download_file(document_id: str) -> dict:
    """Download a file's latest version (e.g. a CIM, IM, or screener) as base64.

    Args:
        document_id: The ContentDocument ID (starts with 069), from list_files
    """
    sf = get_sf_client()
    version = sf.query(
        "SELECT Id, Title, FileExtension, FileType, ContentSize, VersionData "
        "FROM ContentVersion "
        f"WHERE ContentDocumentId = '{document_id}' AND IsLatest = true"
    )
    if not version["records"]:
        return {"error": f"No version found for document {document_id}"}
    record = version["records"][0]
    if record["ContentSize"] > MAX_DOWNLOAD_BYTES:
        return {
            "error": f"File is {record['ContentSize']} bytes; download limit is "
                     f"{MAX_DOWNLOAD_BYTES} bytes."
        }
    host = sf.base_url.split("/services/")[0]
    resp = sf.session.get(
        f"{host}{record['VersionData']}",
        headers={"Authorization": f"Bearer {sf.session_id}"},
        timeout=120,
    )
    resp.raise_for_status()
    logger.info(f"Downloaded ContentDocument {document_id} ({len(resp.content)} bytes)")
    return {
        "title": record["Title"],
        "file_extension": record["FileExtension"],
        "file_type": record["FileType"],
        "size": len(resp.content),
        "content_base64": base64.b64encode(resp.content).decode(),
    }


@mcp.tool()
def attach_file_link(record_id: str, url: str, title: str) -> dict:
    """Attach an external file link to a Salesforce record.

    Creates a ContentVersion with an external URL and links it to the record.
    Use this after uploading a file to S3 or Google Drive to create a
    reference in Salesforce.

    Args:
        record_id: The record to link the file to (e.g. an Opportunity ID)
        url: The external URL where the file is hosted
        title: Display title for the file in Salesforce
    """
    sf = get_sf_client()
    version = sf.ContentVersion.create({
        "Title": title,
        "PathOnClient": title,
        "ExternalDataSourceId": None,
        "ContentUrl": url,
    })
    version_id = version["id"]

    content_doc = sf.query(
        f"SELECT ContentDocumentId FROM ContentVersion WHERE Id = '{version_id}'"
    )
    doc_id = content_doc["records"][0]["ContentDocumentId"]

    sf.ContentDocumentLink.create({
        "ContentDocumentId": doc_id,
        "LinkedEntityId": record_id,
        "ShareType": "V",
    })

    logger.info(f"Attached '{title}' to record {record_id}")
    return {"content_document_id": doc_id, "content_version_id": version_id}
