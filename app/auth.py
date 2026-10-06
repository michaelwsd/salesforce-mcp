import hmac
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.extension import EXTENSION_PATH

VALID_API_KEYS = {
    k.strip()
    for k in os.getenv("MCP_API_KEYS", "").split(",")
    if k.strip()
}


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Public: status page, uptime, the Claude Desktop extension (no secrets in
        # it), and screener downloads (those links carry their own HMAC signature
        # and expiry; see app/screener/downloads.py).
        if request.url.path in ("/", "/api/uptime", EXTENSION_PATH) or request.url.path.startswith("/screeners/"):
            return await call_next(request)

        if not VALID_API_KEYS:
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"error": "Missing Authorization header"}, status_code=401)

        token = auth_header[len("Bearer "):]
        if not any(hmac.compare_digest(token, key) for key in VALID_API_KEYS):
            return JSONResponse({"error": "Invalid API key"}, status_code=401)

        return await call_next(request)
