import os
import uvicorn
from starlette.routing import Route
from app import mcp
from app.auth import ApiKeyAuthMiddleware
from app.status import status_page

if __name__ == "__main__":
    starlette_app = mcp.streamable_http_app()
    starlette_app.add_middleware(ApiKeyAuthMiddleware)
    starlette_app.routes.insert(0, Route("/", status_page))

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)
