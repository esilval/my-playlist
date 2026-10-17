from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx2
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.api import api_client, build_app_with_probe, register

pytestmark = pytest.mark.anyio


@dataclass
class Ctx:
    client: httpx2.AsyncClient
    engine: AsyncEngine
    codes: dict[str, str]


@pytest.fixture
async def ctx(engine: AsyncEngine, database_url: str) -> AsyncIterator[Ctx]:
    async with api_client(build_app_with_probe(database_url)) as client:
        await register(client, "a@ejemplo.com", "contraseña-segura", "Bar La Esquina")
        await register(client, "b@ejemplo.com", "contraseña-segura", "Café Ñandú")
        async with engine.connect() as connection:
            rows = await connection.execute(text("SELECT name, public_code FROM establishment"))
            codes = {row.name: row.public_code for row in rows}
        client.cookies.clear()
        yield Ctx(client=client, engine=engine, codes=codes)


async def _public(ctx: Ctx, code: str) -> httpx2.Response:
    return await ctx.client.get(f"/api/public/establishments/{code}")


async def test_F001_R012_codigo_existente_devuelve_nombre_sin_sesion(ctx: Ctx) -> None:
    for name, code in ctx.codes.items():
        response = await _public(ctx, code)

        assert response.status_code == 200
        # Solo el nombre: ni dirección, ni teléfono, ni identificadores.
        assert response.json() == {"name": name}
        assert "set-cookie" not in response.headers


async def test_F001_R013_codigo_inexistente_da_404(ctx: Ctx) -> None:
    response = await _public(ctx, "ZZZZZZZZZZ")

    assert response.status_code == 404
    assert response.json() == {"error": "not_found"}


async def test_F001_R013_codigo_mal_formado_da_el_mismo_404(ctx: Ctx) -> None:
    known = ctx.codes["Bar La Esquina"]
    expected = (await _public(ctx, "ZZZZZZZZZZ")).content

    malformed = (
        known.lower(),
        known[:-1],
        known + "X",
        "%20",
        "a' OR '1'='1",
        "ñ" * 10,
        "%00" + known[1:],
        "a%2Fb",
        known[:5] + "/" + known[5:],
        known.replace(known[0], "I"),  # fuera del alfabeto Crockford
    )
    for code in malformed:
        response = await _public(ctx, code)
        assert response.status_code == 404, code
        assert response.content == expected, code
