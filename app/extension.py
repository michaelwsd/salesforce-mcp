"""Serves the Claude Desktop extension (.mcpb) built from desktop-extension/.

The Docker image builds it into EXTENSION_FILE; for local runs, build it with
`npm run build` in desktop-extension/. The download is public: the bundle holds
no secrets, and each person enters their own API key when installing it.
"""

from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse, PlainTextResponse

EXTENSION_PATH = "/extension/armitage-salesforce.mcpb"
EXTENSION_FILE = Path(__file__).resolve().parent.parent / "desktop-extension" / "dist" / "armitage-salesforce.mcpb"


async def download_extension(request: Request):
    if not EXTENSION_FILE.is_file():
        return PlainTextResponse("Extension not built. Run `npm run build` in desktop-extension/.", status_code=404)
    return FileResponse(EXTENSION_FILE, media_type="application/zip", filename=EXTENSION_FILE.name)
