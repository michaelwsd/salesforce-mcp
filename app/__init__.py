import os
import logging
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("salesforce-mcp")

mcp = FastMCP(
    "Armitage Salesforce",
    stateless_http=True,
    host="0.0.0.0",
    port=8080,
)

# Register all tools by importing the tools package
import app.tools  # noqa: F401, E402
