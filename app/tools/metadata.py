from app import mcp
from app.client import get_sf_client


@mcp.tool()
def list_objects(custom_only: bool = False) -> dict:
    """List all queryable SObjects (object types) in the Salesforce org.

    Returns the name and label of each object. Use this to discover what
    objects exist before querying them. The org has ~700 queryable objects,
    mostly system ones; the business data lives in Account, Contact, Lead,
    Opportunity, OpportunityContactRole, Task, Event, EmailMessage, Note,
    FeedItem, ContentDocument, Campaign, and the custom objects.

    Args:
        custom_only: Only return custom objects (names ending in __c)
    """
    sf = get_sf_client()
    objects = [
        {"name": obj["name"], "label": obj["label"], "custom": obj["custom"]}
        for obj in sf.describe()["sobjects"]
        if obj["queryable"] and (obj["custom"] or not custom_only)
    ]
    return {"count": len(objects), "objects": objects}


@mcp.tool()
def describe_object(object_type: str) -> dict:
    """Get field and relationship metadata for a Salesforce object.

    Returns each field's name, label, type, whether it is required, and for
    lookups the referenced objects and relationship name (for dot-notation
    like Owner.Name). Also lists child relationships usable in subqueries
    (e.g. SELECT Id, (SELECT Id FROM OpportunityContactRoles) FROM Opportunity).
    Use this to understand what fields are available before querying or
    creating records.

    Args:
        object_type: The Salesforce object type (e.g. Opportunity, Account)
    """
    sf = get_sf_client()
    sobject = getattr(sf, object_type)
    description = sobject.describe()
    fields = []
    for f in description["fields"]:
        field = {
            "name": f["name"],
            "label": f["label"],
            "type": f["type"],
            "required": not f["nillable"] and not f["defaultedOnCreate"],
            "custom": f["custom"],
        }
        if f.get("referenceTo"):
            field["references"] = f["referenceTo"]
            field["relationship_name"] = f.get("relationshipName")
        fields.append(field)
    return {
        "name": description["name"],
        "label": description["label"],
        "fields": fields,
        "child_relationships": [
            {"relationship_name": c["relationshipName"], "child_object": c["childSObject"], "field": c["field"]}
            for c in description["childRelationships"]
            if c.get("relationshipName")
        ],
    }


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
