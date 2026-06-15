from app import mcp
from app.client import get_sf_client


@mcp.tool()
def list_reports() -> dict:
    """List all reports in the Salesforce org.

    Returns report names and IDs. Use the ID with run_report to execute one.
    """
    sf = get_sf_client()
    return sf.query("SELECT Id, Name, FolderName FROM Report ORDER BY Name")


@mcp.tool()
def run_report(report_id: str, filters: dict | None = None) -> dict:
    """Execute a Salesforce report and return its results.

    Args:
        report_id: The 15 or 18 character report ID
        filters: Optional report filter overrides
    """
    sf = get_sf_client()
    body = {"reportMetadata": filters} if filters else {"reportMetadata": {}}
    return sf.restful(f"analytics/reports/{report_id}", method="POST", json=body)


@mcp.tool()
def list_dashboards() -> list[dict]:
    """List all dashboards in the Salesforce org.

    Returns dashboard names and IDs.
    """
    sf = get_sf_client()
    result = sf.restful("analytics/dashboards")
    if isinstance(result, list):
        return result
    return result.get("dashboards", [])
