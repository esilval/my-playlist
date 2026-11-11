"""Registro de cada petición sin datos sensibles (feature 004, plan D11)."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.main import create_app
from app.shared.config import Settings
from app.shared.observability import RequestLogMiddleware

BACKEND_DIR = Path(__file__).resolve().parents[2]
SEARCH = "/api/public/establishments/{code}/search"
SECRET_QUERY = "texto-que-busco-en-privado"


def _app(lines: list[str]) -> FastAPI:
    app = FastAPI()

    @app.get(SEARCH)
    async def search(code: str, q: str = "") -> JSONResponse:
        if q == "caído":
            return JSONResponse({"error": "search_unavailable"}, status_code=503)
        return JSONResponse({"results": [{"title": f"{q} en {code}"}]})

    @app.post("/api/owner/establishment")
    async def update() -> JSONResponse:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    @app.get("/api/owner/me")
    async def me() -> JSONResponse:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    app.add_middleware(RequestLogMiddleware, namespace="MyPlaylist/test", write=lines.append)
    return app


def _requests(lines: list[str]) -> list[dict[str, Any]]:
    entries = [json.loads(line) for line in lines]
    return [entry for entry in entries if entry["event"] == "request"]


def test_F004_R011_cada_peticion_escribe_su_ruta_su_estado_y_su_duracion() -> None:
    lines: list[str] = []
    client = TestClient(_app(lines))

    client.get("/api/public/establishments/ABC123/search", params={"q": "salsa"})
    client.get("/no-existe")

    first, unmatched = _requests(lines)
    assert first["method"] == "GET"
    assert first["route"] == SEARCH
    assert first["status"] == 200
    assert isinstance(first["duration_ms"], float)
    assert first["duration_ms"] >= 0
    # La métrica de la latencia va en la misma línea, con la ruta como dimensión.
    directive = first["_aws"]["CloudWatchMetrics"][0]
    assert directive["Namespace"] == "MyPlaylist/test"
    assert directive["Metrics"] == [{"Name": "RequestLatency", "Unit": "Milliseconds"}]
    assert first["Route"] == SEARCH
    assert first["RequestLatency"] == first["duration_ms"]
    # Una ruta que no existe no deja la que eligió el cliente.
    assert unmatched["status"] == 404
    assert unmatched["route"] == "(sin ruta)"


def test_F004_R016_el_registro_usa_la_plantilla_de_la_ruta_sin_la_cadena_de_consulta() -> None:
    lines: list[str] = []
    client = TestClient(_app(lines))

    response = client.get("/api/public/establishments/ABC123/search", params={"q": SECRET_QUERY})

    assert SECRET_QUERY in response.text
    output = "\n".join(lines)
    assert SECRET_QUERY not in output
    assert "ABC123" not in output
    assert "?" not in output


def test_F004_R016_el_registro_no_escribe_cabeceras_cookies_ni_cuerpos() -> None:
    lines: list[str] = []
    client = TestClient(_app(lines))
    client.cookies.set("mp_session", "valor-de-la-cookie-de-sesion")

    client.post(
        "/api/owner/establishment",
        headers={"Authorization": "Bearer token-secreto", "User-Agent": "agente-del-cliente"},
        json={"password": "contraseña-del-cuerpo"},
    )

    output = "\n".join(lines)
    for secret in (
        "valor-de-la-cookie-de-sesion",
        "token-secreto",
        "agente-del-cliente",
        "contraseña-del-cuerpo",
    ):
        assert secret not in output
    [entry] = _requests(lines)
    assert set(entry) == {
        "ts",
        "level",
        "event",
        "method",
        "route",
        "status",
        "duration_ms",
        "client_ip",
        "_aws",
        "Route",
        "RequestLatency",
    }


def test_F004_R020_solo_los_401_y_403_llevan_la_ip() -> None:
    lines: list[str] = []
    client = TestClient(_app(lines))
    viewer = {"CloudFront-Viewer-Address": "203.0.113.7:51234"}

    client.get("/api/public/establishments/ABC123/search", headers=viewer)
    client.get("/no-existe", headers=viewer)
    client.post("/api/owner/establishment", headers=viewer)
    client.get("/api/owner/me", headers=viewer)

    ok, not_found, unauthorized, forbidden = _requests(lines)
    assert "client_ip" not in ok
    # Otro rechazo, como un 404, tampoco la lleva.
    assert not_found["status"] == 404
    assert "client_ip" not in not_found
    assert unauthorized["client_ip"] == "203.0.113.7"
    assert forbidden["client_ip"] == "203.0.113.7"


def test_F004_R020_la_ip_sale_de_cloudfront_viewer_address_y_no_de_x_forwarded_for() -> None:
    lines: list[str] = []
    client = TestClient(_app(lines))
    forged = "198.51.100.66"

    client.get(
        "/api/owner/me",
        headers={
            "X-Forwarded-For": f"{forged}, 203.0.113.7",
            "CloudFront-Viewer-Address": "[2001:db8::1]:443",
        },
    )
    client.get("/api/owner/me", headers={"X-Forwarded-For": forged})

    with_viewer, without_viewer = _requests(lines)
    assert with_viewer["client_ip"] == "2001:db8::1"
    # Sin la cabecera de CloudFront no hay IP fiable: no se inventa.
    assert without_viewer["client_ip"] is None
    assert forged not in "\n".join(lines)


def test_F004_R011_search_unavailable_cuenta_cada_503() -> None:
    lines: list[str] = []
    client = TestClient(_app(lines))

    client.get("/api/public/establishments/ABC123/search", params={"q": "salsa"})
    client.get("/api/public/establishments/ABC123/search", params={"q": "caído"})
    client.get("/api/public/establishments/ABC123/search", params={"q": "caído"})

    metrics = [json.loads(line) for line in lines if json.loads(line)["event"] == "metric"]
    assert [entry["SearchUnavailable"] for entry in metrics] == [1, 1]
    for entry in metrics:
        directive = entry["_aws"]["CloudWatchMetrics"][0]
        assert directive["Metrics"] == [{"Name": "SearchUnavailable", "Unit": "Count"}]
        assert "caído" not in json.dumps(entry, ensure_ascii=False)


def test_F004_R011_la_api_registra_cada_peticion(capsys: pytest.CaptureFixture[str]) -> None:
    # Sin base de datos, la búsqueda puede acabar en 500: también se registra.
    settings = Settings(_env_file=None)
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        client.get("/api/health")
        client.get("/api/public/establishments/ABCDEFGHIJ/search", params={"q": SECRET_QUERY})

    output = capsys.readouterr().out
    entries = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    [health] = [entry for entry in entries if entry.get("route") == "/api/health"]
    assert health["status"] == 200
    # El del entorno en que corre: `local` en un equipo, `test` en el CI.
    assert health["_aws"]["CloudWatchMetrics"][0]["Namespace"] == f"MyPlaylist/{settings.env}"
    # La plantilla lleva el prefijo del router incluido, sin el código ni la consulta.
    [search] = [entry for entry in entries if entry.get("route") == SEARCH]
    assert search["event"] == "request"
    assert SECRET_QUERY not in output
    assert "ABCDEFGHIJ" not in output


def test_F004_R016_el_arranque_con_configuracion_invalida_no_escribe_valores() -> None:
    visible = "secreto-del-ticket-que-no-debe-aparecer-en-el-registro"
    env = {
        **os.environ,
        "ENV": "production",
        "EMAIL_BACKEND": "ses",
        "DATA_POLICY_VERSION": "2026-10",
        "REALTIME_TICKET_SECRET": visible,
        "CATALOG_PROVIDER": "youtube",
        "YOUTUBE_API_KEY": "clave-de-youtube-que-no-debe-aparecer",
        "DEVICE_TOKEN_SECRET": "corto",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 1
    assert "configuración inválida" in result.stderr
    assert "DEVICE_TOKEN_SECRET" in result.stderr
    for value in (visible, "clave-de-youtube-que-no-debe-aparecer", "'corto'"):
        assert value not in result.stderr
    assert "Traceback" not in result.stderr
