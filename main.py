import os
import uvicorn
from app import mcp
from app.auth import ApiKeyAuthMiddleware

if __name__ == "__main__":
    starlette_app = mcp.streamable_http_app()
    starlette_app.add_middleware(ApiKeyAuthMiddleware)

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)
