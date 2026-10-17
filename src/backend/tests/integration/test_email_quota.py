from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.accounts.application.request_password_reset import RequestPasswordReset
from app.accounts.infrastructure.repositories import SqlAccountsUnitOfWork
from app.shared.db import Database
from tests.integration.api import api_client, build_app_with_probe, register

pytestmark = pytest.mark.anyio

EMAIL = "dueno@ejemplo.com"
PASSWORD = "contraseña-segura"


@dataclass
class Ctx:
    client: httpx2.AsyncClient
    engine: AsyncEngine


@pytest.fixture
async def ctx(engine: AsyncEngine, database_url: str) -> AsyncIterator[Ctx]:
    async with api_client(build_app_with_probe(database_url)) as client:
        await register(client, EMAIL, PASSWORD, "Bar La Esquina")
        yield Ctx(client=client, engine=engine)


async def _count(ctx: Ctx, template: str) -> int:
    async with ctx.engine.connect() as connection:
        result = await connection.execute(
            text("SELECT count(*) FROM email_outbox WHERE template = CAST(:t AS email_template)"),
            {"t": template},
        )
        return int(result.scalar_one())


async def _age_outbox(ctx: Ctx, minutes: int) -> None:
    async with ctx.engine.begin() as connection:
        await connection.execute(
            text("UPDATE email_outbox SET created_at = created_at - CAST(:m AS interval)"),
            {"m": timedelta(minutes=minutes)},
        )


async def test_F001_R027_cuarta_recuperacion_misma_respuesta_sin_encolar(ctx: Ctx) -> None:
    responses = [
        await ctx.client.post("/api/auth/password-reset", json={"email": EMAIL}) for _ in range(4)
    ]

    assert {r.status_code for r in responses} == {202}
    assert len({r.content for r in responses}) == 1  # la cuarta responde igual
    assert await _count(ctx, "password_reset") == 3

    # Pasada la hora, vuelve a enviar.
    await _age_outbox(ctx, 61)
    await ctx.client.post("/api/auth/password-reset", json={"email": EMAIL})
    assert await _count(ctx, "password_reset") == 4


async def test_F001_R027_cuarto_reenvio_da_429(ctx: Ctx) -> None:
    login = await ctx.client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login.status_code == 200

    # La verificación del registro no cuenta: caben 3 reenvíos.
    for _ in range(3):
        assert (await ctx.client.post("/api/owner/email-verification/resend")).status_code == 202
    fourth = await ctx.client.post("/api/owner/email-verification/resend")

    assert fourth.status_code == 429
    assert fourth.json() == {"error": "resend_rate_limited"}
    assert await _count(ctx, "verify_email") == 4  # registro + 3 reenvíos
    async with ctx.engine.connect() as connection:
        live = await connection.execute(
            text(
                "SELECT count(*) FROM email_token "
                "WHERE purpose = 'verify' AND superseded_at IS NULL"
            )
        )
        assert live.scalar_one() == 1  # el 429 no reemplazó el último enlace

    await _age_outbox(ctx, 61)
    assert (await ctx.client.post("/api/owner/email-verification/resend")).status_code == 202


async def test_F001_R027_cuarto_aviso_de_registro_no_se_encola(ctx: Ctx) -> None:
    responses = [await _register_again(ctx) for _ in range(4)]

    assert {r.status_code for r in responses} == {202}
    assert len({r.content for r in responses}) == 1
    assert await _count(ctx, "registration_attempt") == 3


async def _register_again(ctx: Ctx) -> httpx2.Response:
    from app.accounts.domain.data_policy import DRAFT_VERSION

    return await ctx.client.post(
        "/api/auth/register",
        json={
            "email": EMAIL.upper(),
            "password": "otra-contraseña",
            "establishment_name": "Otro bar",
            "data_authorization": True,
            "policy_version": DRAFT_VERSION,
        },
    )


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


async def test_F001_R027_limite_usa_el_reloj_del_caso_de_uso(ctx: Ctx) -> None:
    # Un reloj adelantado un día respecto a la base no anula el límite: la hora de
    # encolado y la del conteo salen del mismo reloj.
    tomorrow = datetime.now(UTC) + timedelta(days=1)
    request_reset = RequestPasswordReset(
        unit_of_work=SqlAccountsUnitOfWork(Database(ctx.engine, role="app_api")),
        clock=FixedClock(tomorrow),
        public_base_url="https://myplaylist.test",
    )

    for _ in range(4):
        await request_reset(EMAIL)

    async with ctx.engine.connect() as connection:
        rows = await connection.execute(
            text("SELECT created_at FROM email_outbox WHERE template = 'password_reset'")
        )
        created = list(rows.scalars())
    assert len(created) == 3
    assert all(abs(at - tomorrow) < timedelta(seconds=1) for at in created)
