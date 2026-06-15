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
def bulk_query(soql: str) -> list[dict]:
    """Run a bulk async query for large datasets.

    Use this instead of regular query() when you expect more than 10,000 records.
    The Bulk API runs the query asynchronously on Salesforce's side and returns
    all results without pagination limits.

    Args:
        soql: The SOQL query string
    """
    sf = get_sf_client()
    object_type = soql.strip().split("FROM")[1].strip().split()[0]
    sobject = getattr(sf.bulk, object_type)
    return sobject.query(soql)
