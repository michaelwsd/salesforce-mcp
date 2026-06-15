from app import mcp
from app.client import get_sf_client


@mcp.tool()
def list_objects() -> list[dict]:
    """List all SObjects (object types) available in the Salesforce org.

    Returns the name and label of each object. Use this to discover what
    objects exist before querying them.
    """
    sf = get_sf_client()
    description = sf.describe()
    return [
        {"name": obj["name"], "label": obj["label"], "custom": obj["custom"]}
        for obj in description["sobjects"]
        if obj["queryable"]
    ]


@mcp.tool()
def describe_object(object_type: str) -> list[dict]:
    """Get field metadata for a Salesforce object.

    Returns the name, label, type, and whether each field is required.
    Use this to understand what fields are available before querying or
    creating records.

    Args:
        object_type: The Salesforce object type (e.g. Opportunity, Account)
    """
    sf = get_sf_client()
    sobject = getattr(sf, object_type)
    description = sobject.describe()
    return [
        {
            "name": f["name"],
            "label": f["label"],
            "type": f["type"],
            "required": not f["nillable"] and not f["defaultedOnCreate"],
            "custom": f["custom"],
        }
        for f in description["fields"]
    ]


@mcp.tool()
def describe_field(object_type: str, field_name: str) -> dict:
    """Get detailed metadata for a specific field, including picklist values.

    Use this when you need to know the allowed values for a picklist field,
    the field's data type, length constraints, or relationship details.

    Args:
        object_type: The Salesforce object type
        field_name: The API name of the field (e.g. StageName, GOWT_Priority__c)
    """
    sf = get_sf_client()
    sobject = getattr(sf, object_type)
    description = sobject.describe()
    for field in description["fields"]:
        if field["name"] == field_name:
            result = {
                "name": field["name"],
                "label": field["label"],
                "type": field["type"],
                "length": field.get("length"),
                "required": not field["nillable"] and not field["defaultedOnCreate"],
                "updateable": field["updateable"],
                "custom": field["custom"],
            }
            if field.get("picklistValues"):
                result["picklist_values"] = [
                    {"value": pv["value"], "label": pv["label"], "active": pv["active"]}
                    for pv in field["picklistValues"]
                ]
            if field.get("referenceTo"):
                result["references"] = field["referenceTo"]
            return result
    return {"error": f"Field '{field_name}' not found on {object_type}"}
