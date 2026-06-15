from app import mcp, logger
from app.client import get_sf_client


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

    Returns the file's latest version info including title, type, and
    a download path you can use to fetch the file content.

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
    return {
        "id": record["Id"],
        "title": record["Title"],
        "file_type": record["FileType"],
        "size": record["ContentSize"],
        "download_path": f"{sf.base_url}{record['VersionData']}",
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
