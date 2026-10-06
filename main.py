import os

import uvicorn
from starlette.routing import Route

from app import mcp
from app.auth import ApiKeyAuthMiddleware
from app.extension import EXTENSION_PATH, download_extension
from app.screener.downloads import DOWNLOAD_PATH, download_screener
from app.status import status_page, uptime_api

if __name__ == "__main__":
    starlette_app = mcp.streamable_http_app()
    starlette_app.add_middleware(ApiKeyAuthMiddleware)
    starlette_app.routes.insert(0, Route("/", status_page))
    starlette_app.routes.insert(1, Route("/api/uptime", uptime_api))
    starlette_app.routes.insert(2, Route(f"{DOWNLOAD_PATH}{{token}}", download_screener))
    starlette_app.routes.insert(3, Route(EXTENSION_PATH, download_extension))

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)
