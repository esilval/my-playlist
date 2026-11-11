"""Registro de cada petición de la API (feature 004, plan D11, ADR-0018).

Una línea JSON por petición, en la salida estándar, con la plantilla de la ruta, el estado
y la duración, y en la misma línea la métrica `RequestLatency` en formato EMF. Sustituye al
registro de acceso de uvicorn, que escribe la cadena de consulta: ahí va el texto que busca
el cliente (R016).

No escribe cabeceras, cookies, cuerpos ni valores de la ruta. Solo los 401 y 403 llevan la
IP de quien los provoca, para la alarma de SG6 (R020). La IP sale de
`CloudFront-Viewer-Address`, que pone CloudFront y el cliente no puede falsear; nunca de
`X-Forwarded-For`, cuyo primer valor sí lo controla quien hace la petición.
"""

import json
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.shared.infrastructure.emf import emf_fields

VIEWER_ADDRESS_HEADER = b"cloudfront-viewer-address"
# Las respuestas que delatan un intento sobre algo ajeno (SG6).
DENIED_STATUSES = frozenset({401, 403})
SEARCH_ROUTE = "/api/public/establishments/{code}/search"
# Peticiones que no casan con ninguna ruta: no se registra su ruta real, que la elige el
# cliente.
UNMATCHED_ROUTE = "(sin ruta)"


def _write_line(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def route_template(scope: Scope) -> str:
    """La plantilla de la ruta que atendió la petición, sin valores ni consulta.

    La ruta solo conoce su parte (`/public/establishments/{code}/search`): el prefijo de
    `include_router` (`/api`) no está en ella. Se recupera del camino real, quitándole la
    parte de la ruta con sus valores. Ese prefijo es fijo, porque la petición casó con la
    ruta, así que no deja nada que elija el cliente. Vale mientras los prefijos de
    `include_router` sean literales, como en `app.main`: uno con parámetros dejaría sus
    valores en el registro.
    """
    route = scope.get("route")
    template = getattr(route, "path_format", None)
    if not isinstance(template, str):
        return UNMATCHED_ROUTE
    path: str = scope.get("path", "")
    params = {name: str(value) for name, value in scope.get("path_params", {}).items()}
    try:
        rendered = template.format(**params)
    except (KeyError, IndexError, ValueError):
        return template
    if rendered and path.endswith(rendered):
        return path[: len(path) - len(rendered)] + template
    return template


def viewer_ip(scope: Scope) -> str | None:
    """La IP de `CloudFront-Viewer-Address` (`ip:puerto`), sin el puerto."""
    for name, value in scope.get("headers", []):
        if name == VIEWER_ADDRESS_HEADER:
            address = value.decode("latin-1").strip()
            ip, separator, port = address.rpartition(":")
            if not separator or not port.isdigit():
                return None
            return ip.strip("[]") or None
    return None


class RequestLogMiddleware:
    def __init__(
        self, app: ASGIApp, *, namespace: str, write: Callable[[str], None] = _write_line
    ) -> None:
        self.app = app
        self.namespace = namespace
        self._write = write

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status = 500

        async def capture_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            self._log(scope, status, (time.perf_counter() - started) * 1000)

    def _log(self, scope: Scope, status: int, duration_ms: float) -> None:
        now = datetime.now(UTC)
        timestamp_ms = int(now.timestamp() * 1000)
        route = route_template(scope)
        duration_ms = round(duration_ms, 1)
        line: dict[str, Any] = {
            "ts": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": "info",
            "event": "request",
            "method": scope["method"],
            "route": route,
            "status": status,
            "duration_ms": duration_ms,
            **emf_fields(
                self.namespace,
                "RequestLatency",
                duration_ms,
                "Milliseconds",
                {"Route": route},
                timestamp_ms,
            ),
        }
        if status in DENIED_STATUSES:
            line["client_ip"] = viewer_ip(scope)
        self._write(json.dumps(line, ensure_ascii=False))
        # La búsqueda solo responde 503 cuando el proveedor de música no la atiende (R012
        # de 003): es la cifra de SG1 junto con su latencia.
        if route == SEARCH_ROUTE and status == 503:
            self._write(
                json.dumps(
                    {
                        "event": "metric",
                        **emf_fields(
                            self.namespace, "SearchUnavailable", 1, "Count", {}, timestamp_ms
                        ),
                    },
                    ensure_ascii=False,
                )
            )
