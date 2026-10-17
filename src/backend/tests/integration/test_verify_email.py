import urllib.parse
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx2
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.accounts.domain.email_token import TokenPurpose
from app.accounts.domain.ports import EmailTokenRecord
from app.accounts.infrastructure.repositories import SqlAccountsRepository
from tests.integration.api import api_client, build_app_with_probe, register

pytestmark = pytest.mark.anyio

EMAIL = "dueno@ejemplo.com"


@dataclass
class Ctx:
    client: httpx2.AsyncClient
    engine: AsyncEngine


@pytest.fixture
async def ctx(engine: AsyncEngine, database_url: str) -> AsyncIterator[Ctx]:
    async with api_client(build_app_with_probe(database_url)) as client:
        await register(client, EMAIL, "contraseña-segura", "Bar La Esquina")
        yield Ctx(client=client, engine=engine)


async def _rows(ctx: Ctx, sql: str) -> list[dict[str, Any]]:
    async with ctx.engine.connect() as connection:
        return [dict(row._mapping) for row in await connection.execute(text(sql))]


async def _verification_links(ctx: Ctx) -> list[str]:
    """Tokens de los enlaces encolados, del más antiguo al más reciente."""
    messages = await _rows(
        ctx,
        "SELECT payload FROM email_outbox WHERE template = 'verify_email' ORDER BY created_at",
    )
    links = [urllib.parse.urlsplit(m["payload"]["link"]) for m in messages]
    return [urllib.parse.parse_qs(link.query)["token"][0] for link in links]


async def _verify(ctx: Ctx, token: str) -> httpx2.Response:
    return await ctx.client.post("/api/auth/verify-email", json={"token": token})


async def _verified(ctx: Ctx) -> bool:
    [account] = await _rows(ctx, "SELECT email_verified_at FROM owner_account")
    return account["email_verified_at"] is not None


async def _login(ctx: Ctx) -> None:
    response = await ctx.client.post(
        "/api/auth/login", json={"email": EMAIL, "password": "contraseña-segura"}
    )
    assert response.status_code == 200


async def test_F001_R025_primer_uso_verifica_y_crea_sesion(ctx: Ctx) -> None:
    [token] = await _verification_links(ctx)
    assert (await ctx.client.get("/api/owner/_probe")).status_code == 401

    response = await _verify(ctx, token)

    assert response.status_code == 200
    assert response.json() == {"status": "verified"}
    assert "mp_session=" in response.headers["set-cookie"]
    panel = await ctx.client.get("/api/owner/_probe")
    assert panel.status_code == 200
    assert panel.json()["email_verified"] is True
    assert await _verified(ctx)


async def test_F001_R017_segundo_uso_devuelve_already_verified_sin_cookie(ctx: Ctx) -> None:
    [token] = await _verification_links(ctx)
    await _verify(ctx, token)
    ctx.client.cookies.clear()

    again = await _verify(ctx, token)

    assert again.status_code == 200
    assert again.json() == {"status": "already_verified"}
    assert "set-cookie" not in again.headers
    assert (await ctx.client.get("/api/owner/_probe")).status_code == 401
    assert len(await _rows(ctx, "SELECT id FROM owner_session")) == 1


async def test_F001_R026_token_alterado_da_400_sin_verificar_ni_cookie(ctx: Ctx) -> None:
    [token] = await _verification_links(ctx)

    for altered in (token[:-1] + ("A" if token[-1] != "A" else "B"), "", "inventado"):
        response = await _verify(ctx, altered)
        assert response.status_code == 400, altered
        assert response.json() == {"error": "invalid_token"}
        assert "set-cookie" not in response.headers

    assert not await _verified(ctx)
    assert await _rows(ctx, "SELECT id FROM owner_session") == []


async def test_F001_R026_token_reemplazado_por_reenvio_da_400(ctx: Ctx) -> None:
    await _login(ctx)
    assert (await ctx.client.post("/api/owner/email-verification/resend")).status_code == 202
    old, new = await _verification_links(ctx)
    ctx.client.cookies.clear()

    response = await _verify(ctx, old)

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_token"}
    assert not await _verified(ctx)
    # El enlace nuevo sí funciona.
    assert (await _verify(ctx, new)).json() == {"status": "verified"}


async def test_F001_R018_reenvio_encola_un_nuevo_enlace_y_marca_superseded_el_anterior(ctx: Ctx) -> None:  # noqa: E501  # fmt: skip
    await _login(ctx)

    response = await ctx.client.post("/api/owner/email-verification/resend")

    assert response.status_code == 202
    assert response.json() == {"status": "check_email"}
    tokens = await _rows(
        ctx,
        "SELECT superseded_at, used_at, expires_at - created_at AS ttl FROM email_token "
        "ORDER BY created_at",
    )
    assert [t["superseded_at"] is not None for t in tokens] == [True, False]
    assert tokens[1]["ttl"] == timedelta(days=7)
    [_, latest] = await _rows(
        ctx, "SELECT to_address, payload FROM email_outbox ORDER BY created_at"
    )
    assert latest["to_address"] == EMAIL
    assert latest["payload"]["establishment_name"] == "Bar La Esquina"


async def test_F001_R018_reenvio_sin_sesion_da_401_y_verificado_da_409(ctx: Ctx) -> None:
    assert (await ctx.client.post("/api/owner/email-verification/resend")).status_code == 401

    [token] = await _verification_links(ctx)
    await _verify(ctx, token)  # deja la sesión iniciada y el correo verificado
    response = await ctx.client.post("/api/owner/email-verification/resend")

    assert response.status_code == 409
    assert response.json() == {"error": "already_verified"}
    assert len(await _verification_links(ctx)) == 1


async def _verify_with_stale_read(ctx: Ctx, token: str, *changes: str) -> httpx2.Response:
    """Lee el token y, antes de marcarlo, otra transacción lo cambia (carrera simulada)."""
    original = SqlAccountsRepository.email_token_by_hash
    reads: list[bytes] = []

    async def read_then_change(
        self: SqlAccountsRepository, token_hash: bytes, purpose: TokenPurpose
    ) -> EmailTokenRecord | None:
        record = await original(self, token_hash, purpose)
        if not reads:
            async with ctx.engine.begin() as connection:
                for change in changes:
                    await connection.execute(text(change))
        reads.append(token_hash)
        return record

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(SqlAccountsRepository, "email_token_by_hash", read_then_change)
        return await _verify(ctx, token)


async def test_F001_R026_reemplazado_durante_la_verificacion_no_verifica(ctx: Ctx) -> None:
    [token] = await _verification_links(ctx)

    response = await _verify_with_stale_read(
        ctx, token, "UPDATE email_token SET superseded_at = now()"
    )

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_token"}
    assert not await _verified(ctx)
    assert await _rows(ctx, "SELECT id FROM owner_session") == []


async def test_F001_R017_uso_concurrente_del_mismo_enlace_abre_una_sola_sesion(ctx: Ctx) -> None:
    [token] = await _verification_links(ctx)

    # La otra petición ya lo usó y verificó el correo antes de este marcado.
    response = await _verify_with_stale_read(
        ctx,
        token,
        "UPDATE email_token SET used_at = now()",
        "UPDATE owner_account SET email_verified_at = now()",
    )

    assert response.status_code == 200
    assert response.json() == {"status": "already_verified"}
    assert "set-cookie" not in response.headers
    assert await _rows(ctx, "SELECT id FROM owner_session") == []


async def _age_tokens(ctx: Ctx, age: timedelta) -> None:
    """Como si el enlace se hubiera emitido hace `age` (con su caducidad de 7 días)."""
    async with ctx.engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE email_token SET created_at = now() - CAST(:age AS interval), "
                "expires_at = now() - CAST(:age AS interval) + interval '7 days'"
            ),
            {"age": age},
        )


async def test_F001_R028_verify_caducado_da_400_expired_token_sin_cookie(ctx: Ctx) -> None:
    [token] = await _verification_links(ctx)
    await _age_tokens(ctx, timedelta(days=8))

    response = await _verify(ctx, token)

    assert response.status_code == 400
    assert response.json() == {"error": "expired_token"}
    assert "set-cookie" not in response.headers
    assert not await _verified(ctx)
    assert await _rows(ctx, "SELECT id FROM owner_session") == []
    # Se puede pedir uno nuevo: tras entrar con la contraseña, el reenvío funciona.
    await _login(ctx)
    assert (await ctx.client.post("/api/owner/email-verification/resend")).status_code == 202


async def test_F001_R028_enlace_de_6_dias_verifica_y_deja_en_el_panel(ctx: Ctx) -> None:
    [token] = await _verification_links(ctx)
    await _age_tokens(ctx, timedelta(days=6))

    response = await _verify(ctx, token)

    assert response.status_code == 200
    assert response.json() == {"status": "verified"}
    assert "mp_session=" in response.headers["set-cookie"]
    assert (await ctx.client.get("/api/owner/_probe")).status_code == 200
