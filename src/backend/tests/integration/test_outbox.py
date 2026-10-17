import asyncio
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.accounts.domain.ports import EmailMessage
from app.shared.config import get_settings
from app.shared.db import Database
from app.shared.email.smtp_mailpit import SmtpEmailSender
from app.shared.email.templates import EmailTemplate
from app.shared.outbox import MAX_ATTEMPTS, OutboxDispatcher, enqueue
from app.worker import run_once
from tests.integration.conftest import BACKEND_DIR

pytestmark = pytest.mark.anyio

MAILPIT_API = os.environ.get("MAILPIT_API_URL", "http://localhost:8025")


@dataclass
class Ctx:
    engine: AsyncEngine  # superusuario, para preparar y leer sin RLS
    api: Database
    worker: Database
    establishment_id: uuid.UUID


@pytest.fixture
async def ctx(engine: AsyncEngine) -> AsyncIterator[Ctx]:
    establishment_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO establishment (id, establishment_id, public_code, name) "
                "VALUES (:id, :id, 'AAAAAAAAAA', 'Bar La Esquina')"
            ),
            {"id": establishment_id},
        )
    yield Ctx(
        engine=engine,
        api=Database(engine, role="app_api"),
        worker=Database(engine, role="app_worker"),
        establishment_id=establishment_id,
    )


async def _enqueue_verification(ctx: Ctx, to: str) -> None:
    async with ctx.api.transaction(establishment_id=ctx.establishment_id) as connection:
        await enqueue(
            connection,
            establishment_id=ctx.establishment_id,
            to_address=to,
            to_address_normalized=to.lower(),
            template=EmailTemplate.VERIFY_EMAIL,
            payload={"establishment_name": "Bar La Esquina", "link": "http://x/verificar?t=abc"},
        )


async def _outbox(ctx: Ctx) -> dict[str, Any]:
    async with ctx.engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT status, attempts, sent_at, next_attempt_at - now() AS wait "
                    "FROM email_outbox"
                )
            )
        ).one()
    return dict(row._mapping)


def _mailpit(method: str, path: str) -> Any:
    request = urllib.request.Request(f"{MAILPIT_API}{path}", method=method)
    with urllib.request.urlopen(request, timeout=5) as response:
        body = response.read()
    return json.loads(body) if body else None


class FlakySender:
    """Falla las primeras `failures` veces y después entrega en memoria."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        if self.failures > 0:
            self.failures -= 1
            raise ConnectionError("SES no responde")
        self.sent.append(message)


async def test_F001_R017_mensaje_en_outbox_se_envia_a_mailpit(ctx: Ctx) -> None:
    to = f"dueno-{uuid.uuid4().hex[:8]}@ejemplo.com"
    await _enqueue_verification(ctx, to)
    settings = get_settings()
    sender = SmtpEmailSender(
        host=settings.smtp_host, port=settings.smtp_port, sender="MyPlaylist <no@example.com>"
    )

    assert await OutboxDispatcher(ctx.worker, sender).dispatch() == 1

    query = urllib.parse.quote(f"to:{to}")
    found: list[dict[str, Any]] = []
    for _ in range(20):
        found = _mailpit("GET", f"/api/v1/search?query={query}")["messages"]
        if found:
            break
        await asyncio.sleep(0.25)
    assert [m["Subject"] for m in found] == ["Verifica tu correo en MyPlaylist"]
    message = _mailpit("GET", f"/api/v1/message/{found[0]['ID']}")
    assert "http://x/verificar?t=abc" in message["Text"]
    assert "Bar La Esquina" in message["Text"]

    state = await _outbox(ctx)
    assert (state["status"], state["attempts"], state["sent_at"] is not None) == ("sent", 1, True)


async def test_reintento_con_espera_exponencial(ctx: Ctx) -> None:
    await _enqueue_verification(ctx, "dueno@ejemplo.com")
    sender = FlakySender(failures=2)
    dispatcher = OutboxDispatcher(ctx.worker, sender)

    assert await dispatcher.dispatch() == 0
    first = await _outbox(ctx)
    assert (first["status"], first["attempts"]) == ("pending", 1)
    assert timedelta(seconds=25) < first["wait"] <= timedelta(seconds=30)

    # Todavía no ha vencido: el trabajador no lo vuelve a tomar.
    assert await dispatcher.dispatch() == 0
    assert (await _outbox(ctx))["attempts"] == 1

    async with ctx.engine.begin() as connection:
        await connection.execute(text("UPDATE email_outbox SET next_attempt_at = now()"))
    assert await dispatcher.dispatch() == 0
    second = await _outbox(ctx)
    assert (second["status"], second["attempts"]) == ("pending", 2)
    assert timedelta(seconds=55) < second["wait"] <= timedelta(seconds=60)

    async with ctx.engine.begin() as connection:
        await connection.execute(text("UPDATE email_outbox SET next_attempt_at = now()"))
    assert await dispatcher.dispatch() == 1
    assert (await _outbox(ctx))["status"] == "sent"
    assert [m.to for m in sender.sent] == ["dueno@ejemplo.com"]


async def test_tras_el_ultimo_intento_queda_fallado(ctx: Ctx) -> None:
    await _enqueue_verification(ctx, "dueno@ejemplo.com")
    async with ctx.engine.begin() as connection:
        await connection.execute(
            text("UPDATE email_outbox SET attempts = :n"), {"n": MAX_ATTEMPTS - 1}
        )

    assert await OutboxDispatcher(ctx.worker, FlakySender(failures=1)).dispatch() == 0

    state = await _outbox(ctx)
    assert (state["status"], state["attempts"]) == ("failed", MAX_ATTEMPTS)


async def test_worker_run_once_purga_login_attempt_antiguos(ctx: Ctx) -> None:
    async with ctx.engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO login_attempt (email_normalized, attempted_at, succeeded) VALUES "
                "('a@ejemplo.com', now() - interval '2 days', false), "
                "('a@ejemplo.com', now(), false)"
            )
        )
    dispatcher = OutboxDispatcher(ctx.worker, FlakySender(failures=0))

    await run_once(ctx.worker, dispatcher, purge=False)
    async with ctx.engine.connect() as connection:
        assert (
            await connection.execute(text("SELECT count(*) FROM login_attempt"))
        ).scalar_one() == 2

    await run_once(ctx.worker, dispatcher, purge=True)
    async with ctx.engine.connect() as connection:
        assert (
            await connection.execute(text("SELECT count(*) FROM login_attempt"))
        ).scalar_one() == 1


async def test_python_m_app_worker_despacha_un_pendiente(ctx: Ctx, database_url: str) -> None:
    await _enqueue_verification(ctx, "dueno@ejemplo.com")
    env = {**os.environ, "DATABASE_URL": database_url, "EMAIL_BACKEND": "memory"}

    result = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "app.worker", "--once"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert (await _outbox(ctx))["status"] == "sent"


async def test_plantillas_coinciden_con_el_tipo_de_la_base_de_datos(ctx: Ctx) -> None:
    async with ctx.engine.connect() as connection:
        values = await connection.execute(text("SELECT unnest(enum_range(NULL::email_template))"))
        assert set(values.scalars()) == {str(template) for template in EmailTemplate}


async def test_lote_sigue_si_otro_trabajador_ya_cerro_un_mensaje(ctx: Ctx) -> None:
    await _enqueue_verification(ctx, "primero@ejemplo.com")
    await _enqueue_verification(ctx, "segundo@ejemplo.com")
    engine = ctx.engine

    class SlowSender(FlakySender):
        """Mientras envía el primero, «otro trabajador» lo da por enviado."""

        async def send(self, message: EmailMessage) -> None:
            if message.to == "primero@ejemplo.com":
                async with engine.begin() as connection:
                    await connection.execute(
                        text("UPDATE email_outbox SET status = 'sent' WHERE to_address = :to"),
                        {"to": message.to},
                    )
            await super().send(message)

    sender = SlowSender(failures=0)

    # outbox_mark del primero falla (ya no está pendiente), pero no aborta el lote.
    assert await OutboxDispatcher(ctx.worker, sender).dispatch() == 1
    assert sorted(m.to for m in sender.sent) == ["primero@ejemplo.com", "segundo@ejemplo.com"]
    async with ctx.engine.connect() as connection:
        statuses = await connection.execute(text("SELECT DISTINCT status FROM email_outbox"))
        assert statuses.scalars().all() == ["sent"]


async def test_payload_incompleto_falla_sin_reintentar(ctx: Ctx) -> None:
    async with ctx.api.transaction(establishment_id=ctx.establishment_id) as connection:
        await enqueue(
            connection,
            establishment_id=ctx.establishment_id,
            to_address="dueno@ejemplo.com",
            to_address_normalized="dueno@ejemplo.com",
            template=EmailTemplate.PASSWORD_RESET,
            payload={},
        )
    sender = FlakySender(failures=0)

    assert await OutboxDispatcher(ctx.worker, sender).dispatch() == 0

    state = await _outbox(ctx)
    assert (state["status"], state["attempts"], sender.sent) == ("failed", 1, [])
