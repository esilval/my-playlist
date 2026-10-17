import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.shared.db import Database

pytestmark = pytest.mark.anyio


@dataclass
class Ctx:
    engine: AsyncEngine  # superusuario, para preparar datos sin RLS
    worker: Database  # como el trabajador: rol app_worker


@pytest.fixture
async def ctx(engine: AsyncEngine) -> AsyncIterator[Ctx]:
    yield Ctx(engine=engine, worker=Database(engine, role="app_worker"))


async def _establishment(connection: AsyncConnection, code: str) -> uuid.UUID:
    establishment_id = uuid.uuid4()
    await connection.execute(
        text(
            "INSERT INTO establishment (id, establishment_id, public_code, name) "
            "VALUES (:id, :id, :code, 'Bar')"
        ),
        {"id": establishment_id, "code": code},
    )
    return establishment_id


async def _enqueue(connection: AsyncConnection, establishment_id: uuid.UUID, to: str) -> uuid.UUID:
    result = await connection.execute(
        text(
            "INSERT INTO email_outbox (establishment_id, to_address, to_address_normalized, "
            "template, payload) VALUES (:e, :to, lower(:to), 'verify_email', '{\"k\": 1}') "
            "RETURNING id"
        ),
        {"e": establishment_id, "to": to},
    )
    return uuid.UUID(str(result.scalar_one()))


async def _claim(connection: AsyncConnection, batch: int) -> set[uuid.UUID]:
    rows = await connection.execute(text("SELECT id FROM outbox_claim(:n)"), {"n": batch})
    return {uuid.UUID(str(row_id)) for row_id in rows.scalars()}


async def test_F001_R015_app_worker_no_lee_tablas_directamente(ctx: Ctx) -> None:
    # Con contexto fijado, para que no falle antes la política RLS y se vea el permiso.
    denied: dict[str, str] = {}
    for table in ("email_outbox", "owner_account", "establishment", "login_attempt"):
        with pytest.raises(DBAPIError) as error:
            async with ctx.worker.transaction(establishment_id=uuid.uuid4()) as connection:
                await connection.execute(text(f"SELECT 1 FROM {table}"))
        denied[table] = str(error.value)

    assert {
        t for t, msg in denied.items() if f"permission denied for table {t}" not in msg
    } == set()

    async with ctx.engine.connect() as connection:
        grants = await connection.execute(
            text("SELECT count(*) FROM information_schema.role_table_grants WHERE grantee = :r"),
            {"r": "app_worker"},
        )
        assert grants.scalar_one() == 0


async def test_F001_R017_outbox_claim_reparte_sin_duplicar(ctx: Ctx) -> None:
    async with ctx.engine.begin() as connection:
        a = await _establishment(connection, "AAAAAAAAAA")
        b = await _establishment(connection, "BBBBBBBBBB")
        queued = {
            await _enqueue(connection, a, "a1@ejemplo.com"),
            await _enqueue(connection, a, "a2@ejemplo.com"),
            await _enqueue(connection, b, "b1@ejemplo.com"),
        }

    # Dos trabajadores a la vez: el segundo salta las filas que el primero tiene
    # bloqueadas, sin esperar ni repetirlas.
    async with ctx.worker.transaction() as first, ctx.worker.transaction() as second:
        claimed_first = await _claim(first, 2)
        claimed_second = await _claim(second, 10)

    assert len(claimed_first) == 2
    assert claimed_first.isdisjoint(claimed_second)
    assert claimed_first | claimed_second == queued

    # Arrendados: no vuelven a salir hasta que venza el plazo.
    async with ctx.worker.transaction() as connection:
        assert await _claim(connection, 10) == set()


async def test_F001_R017_outbox_claim_devuelve_datos_y_cuenta_intentos(ctx: Ctx) -> None:
    async with ctx.engine.begin() as connection:
        a = await _establishment(connection, "AAAAAAAAAA")
        message_id = await _enqueue(connection, a, "A@Ejemplo.com")

    async with ctx.worker.transaction() as connection:
        rows = await connection.execute(text("SELECT * FROM outbox_claim(10)"))
        assert list(rows.keys()) == ["id", "to_address", "template", "payload", "attempts"]
        assert [tuple(row) for row in rows] == [
            (message_id, "A@Ejemplo.com", "verify_email", {"k": 1}, 1)
        ]


async def test_outbox_claim_recupera_mensajes_con_arrendamiento_vencido(ctx: Ctx) -> None:
    async with ctx.engine.begin() as connection:
        a = await _establishment(connection, "AAAAAAAAAA")
        message_id = await _enqueue(connection, a, "a@ejemplo.com")

    async with ctx.worker.transaction() as connection:
        rows = await connection.execute(
            text("SELECT id FROM outbox_claim(10, interval '-1 second')")
        )
        assert rows.scalars().all() == [message_id]
    async with ctx.worker.transaction() as connection:
        again = await connection.execute(text("SELECT attempts FROM outbox_claim(10)"))
        assert again.scalars().all() == [2]


async def test_outbox_mark_actualiza_estado(ctx: Ctx) -> None:
    async with ctx.engine.begin() as connection:
        a = await _establishment(connection, "AAAAAAAAAA")
        sent = await _enqueue(connection, a, "sent@ejemplo.com")
        retry = await _enqueue(connection, a, "retry@ejemplo.com")
        failed = await _enqueue(connection, a, "failed@ejemplo.com")

    async with ctx.worker.transaction() as connection:
        await _claim(connection, 10)
        await connection.execute(text("SELECT outbox_mark(:id, 'sent')"), {"id": sent})
        await connection.execute(
            text("SELECT outbox_mark(:id, 'pending', now() + interval '1 minute')"),
            {"id": retry},
        )
        await connection.execute(text("SELECT outbox_mark(:id, 'failed')"), {"id": failed})

    async with ctx.engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT id, status, sent_at IS NOT NULL, "
                "next_attempt_at BETWEEN now() + interval '50 seconds' "
                "AND now() + interval '70 seconds' FROM email_outbox"
            )
        )
        state = {row[0]: tuple(row[1:]) for row in rows}

    assert state[sent] == ("sent", True, False)
    assert state[retry] == ("pending", False, True)
    assert state[failed][:2] == ("failed", False)


async def test_outbox_mark_rechaza_reintento_sin_hora_y_mensaje_inexistente(ctx: Ctx) -> None:
    async with ctx.engine.begin() as connection:
        a = await _establishment(connection, "AAAAAAAAAA")
        message_id = await _enqueue(connection, a, "a@ejemplo.com")

    async with ctx.worker.transaction() as connection:
        await connection.execute(text("SELECT outbox_mark(:id, 'sent')"), {"id": message_id})

    errors: list[str] = []
    for sql, params in (
        ("SELECT outbox_mark(:id, 'pending')", {"id": message_id}),
        ("SELECT outbox_mark(:id, 'sent')", {"id": uuid.uuid4()}),
        ("SELECT outbox_mark(:id, 'pending', now())", {"id": message_id}),
    ):
        with pytest.raises(DBAPIError) as error:
            async with ctx.worker.transaction() as connection:
                await connection.execute(text(sql), params)
        errors.append(str(error.value))

    assert "un reintento necesita p_retry_at" in errors[0]
    assert "no existe o ya no está pendiente" in errors[1]
    assert "no existe o ya no está pendiente" in errors[2]  # un enviado no se reabre


async def test_outbox_claim_con_lote_no_positivo_no_reclama(ctx: Ctx) -> None:
    async with ctx.engine.begin() as connection:
        a = await _establishment(connection, "AAAAAAAAAA")
        await _enqueue(connection, a, "a@ejemplo.com")

    async with ctx.worker.transaction() as connection:
        assert await _claim(connection, 0) == set()
        assert await _claim(connection, -1) == set()


async def test_purga_login_attempt_antiguos(ctx: Ctx) -> None:
    async with ctx.engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO login_attempt (email_normalized, attempted_at, succeeded) VALUES "
                "('a@ejemplo.com', now() - interval '2 days', false), "
                "('a@ejemplo.com', now() - interval '1 hour', false)"
            )
        )

    async with ctx.worker.transaction() as connection:
        purged = await connection.execute(text("SELECT login_attempt_purge()"))
        assert purged.scalar_one() == 1

    async with ctx.engine.connect() as connection:
        left = await connection.execute(text("SELECT count(*) FROM login_attempt"))
        assert left.scalar_one() == 1


async def test_app_api_no_ejecuta_funciones_del_trabajador(ctx: Ctx) -> None:
    api = Database(ctx.engine, role="app_api")
    with pytest.raises(DBAPIError) as denied:
        async with api.transaction() as connection:
            await connection.execute(text("SELECT * FROM outbox_claim(1)"))
    assert "permission denied for function outbox_claim" in str(denied.value)
