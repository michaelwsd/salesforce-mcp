import os
import logging
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("salesforce-mcp")

INSTRUCTIONS = """\
Full access to the Armitage Associates Salesforce org (private equity deal
origination) plus GOWT Excel data on OneDrive.

Data model: Opportunity is the core deal record (one per company approached),
Account is the company, Contact/Lead are people, OpportunityContactRole links
people to deals. Notes live in Event/Task Description fields, classic Notes,
and ContentNotes; emails in EmailMessage. Prefer get_company_overview,
get_notes, get_activities, and get_emails for a single deal or company.

Gotchas:
- Tasks/Events older than ~1 year are archived and hidden from normal SOQL
  (most historical meeting notes). The notes/activity tools include them; for
  raw SOQL on Task/Event pass include_archived=True with "IsDeleted = false".
- Many Opportunity fields have legacy names like fid14__c; call
  get_opportunity_field_map to translate them.
- Results are capped per call; use COUNT() and aggregates for org-wide
  questions rather than paging through every record.
"""

mcp = FastMCP(
    "Armitage Salesforce",
    instructions=INSTRUCTIONS,
    stateless_http=True,
    host="0.0.0.0",
    port=8080,
)

# Register all tools by importing the tools package
import app.tools  # noqa: F401, E402
