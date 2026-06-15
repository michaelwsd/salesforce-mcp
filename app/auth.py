import os
import hmac
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

VALID_API_KEYS = set(
    k.strip()
    for k in os.getenv("MCP_API_KEYS", "").split(",")
    if k.strip()
)


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/":
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
