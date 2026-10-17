from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx2
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.api import PUBLIC_BASE_URL, api_client, build_app_with_probe, register

pytestmark = pytest.mark.anyio


@dataclass
class Ctx:
    client: httpx2.AsyncClient
    engine: AsyncEngine


@pytest.fixture
async def ctx(engine: AsyncEngine, database_url: str) -> AsyncIterator[Ctx]:
    async with api_client(build_app_with_probe(database_url)) as client:
        await register(client, "b@ejemplo.com", "contraseña-segura", "Café Ñandú")
        await register(client, "a@ejemplo.com", "contraseña-segura", "Bar La Esquina")
        login = await client.post(
            "/api/auth/login", json={"email": "a@ejemplo.com", "password": "contraseña-segura"}
        )
        assert login.status_code == 200
        yield Ctx(client=client, engine=engine)


async def _row(ctx: Ctx, name: str) -> dict[str, Any]:
    async with ctx.engine.connect() as connection:
        row = (
            await connection.execute(
                text("SELECT * FROM establishment WHERE name = :n"), {"n": name}
            )
        ).one()
    return dict(row._mapping)


async def _patch(ctx: Ctx, body: dict[str, Any]) -> httpx2.Response:
    return await ctx.client.patch("/api/owner/establishment", json=body)


async def test_F001_R014_owner_me_devuelve_cuenta_y_establecimiento(ctx: Ctx) -> None:
    own = await _row(ctx, "Bar La Esquina")

    response = await ctx.client.get("/api/owner/me")

    assert response.status_code == 200
    assert response.json() == {
        "account": {"email": "a@ejemplo.com", "email_verified": False},
        "establishment": {
            "name": "Bar La Esquina",
            "address": None,
            "phone": None,
            "public_url": f"{PUBLIC_BASE_URL}/l/{own['public_code']}",
        },
    }


async def test_F001_R014_editar_nombre_mantiene_public_code(ctx: Ctx) -> None:
    before = await _row(ctx, "Bar La Esquina")

    response = await _patch(ctx, {"name": "La Esquina Bar"})

    assert response.status_code == 200
    assert response.json()["name"] == "La Esquina Bar"
    after = await _row(ctx, "La Esquina Bar")
    assert (after["id"], after["public_code"]) == (before["id"], before["public_code"])
    # Distinto, sin suponer que los relojes de la API y de la base van sincronizados.
    assert after["updated_at"] != before["updated_at"]
    me = (await ctx.client.get("/api/owner/me")).json()
    assert me["establishment"]["name"] == "La Esquina Bar"
    assert me["establishment"]["public_url"].endswith(before["public_code"])


async def test_F001_R014_pagina_publica_muestra_el_nombre_nuevo(ctx: Ctx) -> None:
    code = (await _row(ctx, "Bar La Esquina"))["public_code"]

    await _patch(ctx, {"name": "La Esquina Bar"})
    public = await ctx.client.get(f"/api/public/establishments/{code}")

    assert public.json() == {"name": "La Esquina Bar"}


async def test_F001_R014_nombre_vacio_da_422_y_no_cambia(ctx: Ctx) -> None:
    response = await _patch(ctx, {"name": "  "})

    assert response.status_code == 422
    assert response.json() == {"errors": {"name": "required"}}
    assert (await _row(ctx, "Bar La Esquina"))["name"] == "Bar La Esquina"


async def test_F001_R019_sin_verificar_puede_editar_telefono(ctx: Ctx) -> None:
    assert (await ctx.client.get("/api/owner/me")).json()["account"]["email_verified"] is False

    response = await _patch(ctx, {"phone": "3001234567", "address": "Calle 1 # 2-3"})

    assert response.status_code == 200
    row = await _row(ctx, "Bar La Esquina")
    assert (row["phone"], row["address"]) == ("3001234567", "Calle 1 # 2-3")
    # Vaciar un campo opcional y no tocar los que no llegan.
    await _patch(ctx, {"address": ""})
    row = await _row(ctx, "Bar La Esquina")
    assert (row["phone"], row["address"]) == ("3001234567", None)


async def test_F001_R015_owner_me_sin_sesion_da_401(ctx: Ctx) -> None:
    ctx.client.cookies.clear()

    me = await ctx.client.get("/api/owner/me")
    patch = await _patch(ctx, {"name": "Hackeado"})

    assert me.status_code == patch.status_code == 401
    assert "Bar La Esquina" not in me.text
    assert (await _row(ctx, "Bar La Esquina"))["name"] == "Bar La Esquina"


async def test_F001_R015_patch_ignora_establishment_id_en_el_cuerpo(ctx: Ctx) -> None:
    other = await _row(ctx, "Café Ñandú")

    response = await _patch(
        ctx,
        {"name": "Renombrado", "establishment_id": str(other["id"]), "id": str(other["id"])},
    )

    assert response.status_code == 200
    # Cambia el de la sesión; el otro queda igual.
    assert (await _row(ctx, "Café Ñandú"))["name"] == "Café Ñandú"
    assert (await _row(ctx, "Renombrado"))["id"] != other["id"]


async def test_F001_R009_patch_no_cambia_el_codigo_publico(ctx: Ctx) -> None:
    before = await _row(ctx, "Bar La Esquina")

    response = await _patch(ctx, {"public_code": "ZZZZZZZZZZ"})

    assert response.status_code == 200
    assert (await _row(ctx, "Bar La Esquina"))["public_code"] == before["public_code"]
