from app import mcp, logger
from app.client import get_sf_client


def _page(sf, result: dict, max_records: int, include_archived: bool) -> dict:
    """Follow nextRecordsUrl until at least max_records are collected or the end.

    Whole Salesforce pages (up to 2000 records) are always returned so that
    next_records_url resumes exactly where this call stopped.
    """
    records = list(result["records"])
    while not result["done"] and len(records) < max_records:
        result = sf.query_more(
            result["nextRecordsUrl"], identifier_is_url=True, include_deleted=include_archived
        )
        records.extend(result["records"])
    return {
        "totalSize": result["totalSize"],
        "returned": len(records),
        "done": result["done"],
        # Pass to query_more to continue. Only set when more records remain.
        "next_records_url": result.get("nextRecordsUrl"),
        "records": records,
    }


@mcp.tool()
def query(soql: str, include_archived: bool = False, max_records: int = 2000) -> dict:
    """Run a SOQL query against Salesforce.

    SOQL (Salesforce Object Query Language) is like SQL but for Salesforce.
    Example: SELECT Id, Name, StageName FROM Opportunity WHERE StageName != '7. Killed' LIMIT 10

    Tips:
    - SELECT COUNT() FROM X returns the count in totalSize.
    - SELECT FIELDS(ALL) FROM X LIMIT 200 returns every field (LIMIT <= 200 required).
    - Long text fields (e.g. Description) can't be used in WHERE clauses.

    IMPORTANT: Salesforce archives Tasks and Events older than ~1 year, and the
    normal query hides them. In this org that is ~75% of Tasks and ~96% of
    Events, i.e. most historical meeting notes. When querying Task or Event
    (or counting them), set include_archived=True and add
    "IsDeleted = false" to the WHERE clause to exclude recycle-bin records.

    Args:
        soql: The SOQL query
        include_archived: Use queryAll, which also returns archived activities
            and soft-deleted (recycle bin) records
        max_records: Stop fetching once this many records are collected (default
            2000; results come in pages of up to 2000). If more match, done=False
            and next_records_url is set; pass it to query_more for the next batch.
            Prefer filters, aggregates, or COUNT() over paging through huge
            result sets.
    """
    sf = get_sf_client()
    result = sf.query(soql, include_deleted=include_archived)
    return _page(sf, result, max_records, include_archived)


@mcp.tool()
def query_more(next_records_url: str, include_archived: bool = False, max_records: int = 2000) -> dict:
    """Fetch the next batch of a large query() result.

    Args:
        next_records_url: The next_records_url returned by query or query_more
        include_archived: Must match the include_archived value of the original query
        max_records: Stop fetching once this many records are collected (default 2000)
    """
    sf = get_sf_client()
    result = sf.query_more(next_records_url, identifier_is_url=True, include_deleted=include_archived)
    return _page(sf, result, max_records, include_archived)


@mcp.tool()
def search(sosl: str) -> dict:
    """Run a SOSL search across multiple Salesforce objects.

    SOSL (Salesforce Object Search Language) is a full-text search across
    multiple objects at once. Use this when you want to find something but
    don't know which object it's in.

    Example: FIND {Armitage} IN ALL FIELDS RETURNING Account(Name), Contact(Name, Email)
    """
    sf = get_sf_client()
    return sf.search(sosl)


@mcp.tool()
def get_record(object_type: str, record_id: str, fields: list[str] | None = None) -> dict:
    """Get a single Salesforce record by its object type and ID.

    Args:
        object_type: The Salesforce object type (e.g. Account, Opportunity, Contact)
        record_id: The 18-character Salesforce record ID
        fields: Optional list of specific fields to return. If omitted, returns all fields.
    """
    sf = get_sf_client()
    if fields:
        field_list = ", ".join(fields)
        # queryAll so archived Tasks/Events can be fetched by Id too.
        result = sf.query(
            f"SELECT {field_list} FROM {object_type} WHERE Id = '{record_id}'",
            include_deleted=True,
        )
        return result["records"][0] if result["records"] else {"error": "Record not found"}
    sobject = getattr(sf, object_type)
    return sobject.get(record_id)


@mcp.tool()
def create_record(object_type: str, data: dict) -> dict:
    """Create a new Salesforce record.

    Args:
        object_type: The Salesforce object type (e.g. Account, Contact, Task)
        data: Dictionary of field names and values. Field names must match the API names
              in Salesforce (e.g. "Name", "StageName", "Growth_News__c").
    """
    sf = get_sf_client()
    sobject = getattr(sf, object_type)
    result = sobject.create(data)
    logger.info(f"Created {object_type} record: {result}")
    return result


@mcp.tool()
def update_record(object_type: str, record_id: str, data: dict) -> dict:
    """Update an existing Salesforce record.

    Args:
        object_type: The Salesforce object type
        record_id: The 18-character Salesforce record ID
        data: Dictionary of field names and new values to set
    """
    sf = get_sf_client()
    sobject = getattr(sf, object_type)
    result = sobject.update(record_id, data)
    logger.info(f"Updated {object_type} {record_id}: {data}")
    return result


@mcp.tool()
def delete_record(object_type: str, record_id: str) -> dict:
    """Delete a Salesforce record.

    Args:
        object_type: The Salesforce object type
        record_id: The 18-character Salesforce record ID
    """
    sf = get_sf_client()
    sobject = getattr(sf, object_type)
    result = sobject.delete(record_id)
    logger.info(f"Deleted {object_type} {record_id}")
    return result
