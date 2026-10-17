"""Protección CSRF y cabeceras de transporte (plan D9).

La cookie de sesión es SameSite=Lax y de primera parte; además, toda petición que
modifica algo bajo /api tiene que traer la cabecera propia de la SPA y, si el
navegador manda Origin, que sea el de la SPA.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

CLIENT_HEADER = "x-myplaylist-client"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
HSTS = "max-age=63072000; includeSubDomains"


class CsrfMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, allowed_origin: str) -> None:
        super().__init__(app)
        self._allowed_origin = allowed_origin.rstrip("/")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in SAFE_METHODS and request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if CLIENT_HEADER not in request.headers or (
                origin is not None and origin.rstrip("/") != self._allowed_origin
            ):
                return JSONResponse(status_code=403, content={"error": "csrf"})
        return await call_next(request)


class HstsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = HSTS
        return response
