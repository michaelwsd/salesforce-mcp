import re

from app import mcp, logger
from app.client import get_sf_client


@mcp.tool()
def bulk_upsert(object_type: str, external_id_field: str, records: list[dict]) -> dict:
    """Upsert (insert or update) multiple records in bulk.

    "Upsert" means: if a record with the given external ID exists, update it.
    If it doesn't exist, create it. This is useful for syncing data.

    Args:
        object_type: The Salesforce object type
        external_id_field: The field to match existing records on (e.g. "External_Id__c")
        records: List of record dictionaries to upsert
    """
    sf = get_sf_client()
    sobject = getattr(sf.bulk, object_type)
    result = sobject.upsert(records, external_id_field, batch_size=200)
    logger.info(f"Bulk upserted {len(records)} {object_type} records")
    return {"results": result}


@mcp.tool()
def bulk_query(soql: str, include_archived: bool = False, max_records: int = 50000) -> dict:
    """Run a bulk async query for large datasets.

    Use this instead of query() when you expect tens of thousands of records.
    The Bulk API runs the query asynchronously on Salesforce's side. It does not
    support subqueries, aggregates (COUNT, GROUP BY), or FIELDS(ALL).

    Args:
        soql: The SOQL query string
        include_archived: Use queryAll, which also returns archived Tasks/Events
            (older than ~1 year) and soft-deleted records. Add
            "IsDeleted = false" to the WHERE clause to exclude deleted ones.
        max_records: Maximum records to return (default 50000). total reports
            the full count when truncated.
    """
    match = re.search(r"\bFROM\s+(\w+)", soql, re.IGNORECASE)
    if not match:
        return {"error": "Could not find a FROM clause in the query."}
    sf = get_sf_client()
    sobject = getattr(sf.bulk, match.group(1))
    records = sobject.query_all(soql) if include_archived else sobject.query(soql)
    return {
        "total": len(records),
        "returned": min(len(records), max_records),
        "truncated": len(records) > max_records,
        "records": records[:max_records],
    }
