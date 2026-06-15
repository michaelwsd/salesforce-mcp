from app import mcp, logger
from app.client import get_sf_client


@mcp.tool()
def query(soql: str) -> dict:
    """Run a SOQL query against Salesforce.

    SOQL (Salesforce Object Query Language) is like SQL but for Salesforce.
    Example: SELECT Id, Name, StageName FROM Opportunity WHERE StageName != '7. Killed' LIMIT 10

    Returns all matching records, automatically handling pagination for large result sets.
    """
    sf = get_sf_client()
    return sf.query_all(soql)


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
        result = sf.query(
            f"SELECT {field_list} FROM {object_type} WHERE Id = '{record_id}'"
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
