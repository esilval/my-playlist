import asyncio
import uuid

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from tests.integration.conftest import alembic_config

pytestmark = pytest.mark.anyio


async def _as_api(connection: AsyncConnection, establishment_id: uuid.UUID) -> None:
    await connection.execute(text("SET LOCAL ROLE app_api"))
    await connection.execute(
        text("SELECT set_config('app.establishment_id', :id, true)"), {"id": str(establishment_id)}
    )


async def _establishment(connection: AsyncConnection, public_code: str) -> uuid.UUID:
    establishment_id = uuid.uuid4()
    await connection.execute(
        text(
            "INSERT INTO establishment (id, establishment_id, public_code, name) "
            "VALUES (:id, :id, :code, 'Bar La Esquina')"
        ),
        {"id": establishment_id, "code": public_code},
    )
    return establishment_id


async def _open_session(connection: AsyncConnection, establishment_id: uuid.UUID) -> uuid.UUID:
    created = await connection.execute(
        text("INSERT INTO music_session (establishment_id) VALUES (:e) RETURNING id"),
        {"e": establishment_id},
    )
    created_id: uuid.UUID = created.scalar_one()
    return created_id


async def _queue_item(
    connection: AsyncConnection,
    establishment_id: uuid.UUID,
    session_id: uuid.UUID,
    position: int,
    state: str = "pending",
) -> uuid.UUID:
    created = await connection.execute(
        text(
            "INSERT INTO queue_item (establishment_id, session_id, position, track_ref, title, state) "  # noqa: E501
            "VALUES (:e, :s, :p, 'fake:3s', 'Canción', CAST(:state AS queue_item_state)) RETURNING id"  # noqa: E501
        ),
        {"e": establishment_id, "s": session_id, "p": position, "state": state},
    )
    created_id: uuid.UUID = created.scalar_one()
    return created_id


async def test_F002_R003_una_sola_sesion_abierta_por_establecimiento(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        a = await _establishment(connection, "AAAAAAAAAA")
        await _open_session(connection, a)

    with pytest.raises(IntegrityError, match="music_session_one_open_idx"):
        async with engine.begin() as connection:
            await _open_session(connection, a)

    # Con la anterior cerrada, se puede abrir otra.
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE music_session SET closed_at = now() WHERE establishment_id = :e"),
            {"e": a},
        )
        await _open_session(connection, a)
        sessions = await connection.execute(
            text("SELECT count(*) FILTER (WHERE closed_at IS NULL), count(*) FROM music_session")
        )
        assert sessions.one() == (1, 2)


async def test_F002_R006_una_sola_cancion_sonando_por_sesion(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        a = await _establishment(connection, "AAAAAAAAAA")
        session = await _open_session(connection, a)
        await _queue_item(connection, a, session, 1, "playing")

    with pytest.raises(IntegrityError, match="queue_item_one_playing_idx"):
        async with engine.begin() as connection:
            await _queue_item(connection, a, session, 2, "playing")

    # Las que ya sonaron no cuentan: varias en `played` conviven con una en `playing`.
    async with engine.begin() as connection:
        await _queue_item(connection, a, session, 2, "played")
        await _queue_item(connection, a, session, 3, "played")


async def test_F002_R013_rls_oculta_sesiones_y_cola_de_otro_establecimiento(engine: AsyncEngine) -> None:  # noqa: E501  # fmt: skip
    async with engine.begin() as connection:
        a = await _establishment(connection, "AAAAAAAAAA")
        b = await _establishment(connection, "BBBBBBBBBB")
        session_a = await _open_session(connection, a)
        session_b = await _open_session(connection, b)
        await _queue_item(connection, a, session_a, 1)
        await _queue_item(connection, b, session_b, 1)

    async with engine.begin() as connection:
        await _as_api(connection, a)
        sessions = await connection.execute(text("SELECT establishment_id FROM music_session"))
        assert sessions.scalars().all() == [a]
        items = await connection.execute(text("SELECT establishment_id FROM queue_item"))
        assert items.scalars().all() == [a]

        closed = await connection.execute(
            text("UPDATE music_session SET closed_at = now() WHERE id = :s"), {"s": session_b}
        )
        assert closed.rowcount == 0
        discarded = await connection.execute(
            text("UPDATE queue_item SET state = 'discarded' WHERE session_id = :s"),
            {"s": session_b},
        )
        assert discarded.rowcount == 0

    async with engine.connect() as connection:
        untouched = await connection.execute(
            text(
                "SELECT s.closed_at IS NULL, i.state::text FROM music_session s "
                "JOIN queue_item i ON i.session_id = s.id WHERE s.id = :s"
            ),
            {"s": session_b},
        )
        assert untouched.one() == (True, "pending")


async def test_F002_R013_no_crea_sesion_ni_cancion_en_otro_establecimiento(engine: AsyncEngine) -> None:  # noqa: E501  # fmt: skip
    async with engine.begin() as connection:
        a = await _establishment(connection, "AAAAAAAAAA")
        b = await _establishment(connection, "BBBBBBBBBB")
        session_b = await _open_session(connection, b)

    with pytest.raises(DBAPIError, match="row-level security"):
        async with engine.begin() as connection:
            await _as_api(connection, a)
            await _open_session(connection, b)

    with pytest.raises(DBAPIError, match="row-level security"):
        async with engine.begin() as connection:
            await _as_api(connection, a)
            await _queue_item(connection, b, session_b, 1)


async def test_F002_R013_cancion_no_apunta_a_sesion_de_otro_establecimiento(engine: AsyncEngine) -> None:  # noqa: E501  # fmt: skip
    async with engine.begin() as connection:
        a = await _establishment(connection, "AAAAAAAAAA")
        b = await _establishment(connection, "BBBBBBBBBB")
        session_b = await _open_session(connection, b)

    # Aunque se salte RLS (dueño de la tabla), la clave foránea compuesta lo impide.
    with pytest.raises(IntegrityError, match="queue_item_session_id_establishment_id_fkey"):
        async with engine.begin() as connection:
            await _queue_item(connection, a, session_b, 1)


async def test_F002_R013_app_worker_sin_acceso_a_sesiones(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT t, p, has_table_privilege(r, t, p) "
                "FROM unnest(ARRAY['music_session', 'queue_item']) AS t, "
                "unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) AS p, "
                "unnest(ARRAY['app_worker']) AS r"
            )
        )
        granted = {(table, privilege) for table, privilege, allowed in rows if allowed}

    assert granted == set()


def _public_objects(database_url: str) -> set[str]:
    async def query() -> set[str]:
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as connection:
                rows = await connection.execute(
                    text(
                        """
                        SELECT 'table:' || relname FROM pg_class c
                          JOIN pg_namespace n ON n.oid = c.relnamespace
                         WHERE n.nspname = 'public' AND c.relkind = 'r'
                        UNION ALL
                        SELECT 'type:' || typname FROM pg_type t
                          JOIN pg_namespace n ON n.oid = t.typnamespace
                         WHERE n.nspname = 'public' AND t.typtype = 'e'
                        """
                    )
                )
                return set(rows.scalars())
        finally:
            await engine.dispose()

    return asyncio.run(query())


def test_migracion_0002_baja_a_0001_y_sube(database_url: str) -> None:
    config = alembic_config(database_url)
    added = {"table:music_session", "table:queue_item", "type:queue_item_state"}

    command.downgrade(config, "0001_accounts")
    objects = _public_objects(database_url)
    assert not added & objects
    assert "table:establishment" in objects

    command.upgrade(config, "head")
    assert added <= _public_objects(database_url)


# Las columnas de queue_item. Del cliente solo se guarda requested_by: el identificador
# anónimo de su dispositivo, sin nombre, correo, teléfono ni ubicación (S9).
QUEUE_ITEM_COLUMNS = {
    ("id", "uuid", "NO"),
    ("establishment_id", "uuid", "NO"),
    ("session_id", "uuid", "NO"),
    ("position", "bigint", "NO"),
    ("track_ref", "text", "NO"),
    ("title", "text", "NO"),
    ("state", "USER-DEFINED", "NO"),
    ("failure_reason", "text", "YES"),
    ("created_at", "timestamp with time zone", "NO"),
    ("started_at", "timestamp with time zone", "YES"),
    ("finished_at", "timestamp with time zone", "YES"),
    ("requested_by", "uuid", "YES"),
}


async def test_F003_R002_queue_item_solo_guarda_el_dispositivo_del_cliente(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'queue_item'"
            )
        )
        columns = {(name, data_type, nullable) for name, data_type, nullable in rows}

    assert columns == QUEUE_ITEM_COLUMNS


async def test_F003_R006_indice_parcial_de_pendientes_por_dispositivo(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        definition = (
            await connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = 'queue_item' "
                    "AND indexname = 'queue_item_pending_by_device_idx'"
                )
            )
        ).scalar_one()

    assert "(session_id, requested_by)" in definition
    assert "WHERE (state = 'pending'::queue_item_state)" in definition


async def test_F003_R002_la_api_guarda_el_dispositivo_y_rls_lo_aisla(engine: AsyncEngine) -> None:
    device = uuid.uuid4()
    async with engine.begin() as connection:
        a = await _establishment(connection, "AAAAAAAAAA")
        b = await _establishment(connection, "BBBBBBBBBB")
        item = await _queue_item(connection, a, await _open_session(connection, a), 1)

    # La API del establecimiento A guarda el dispositivo que pidió la canción…
    async with engine.begin() as connection:
        await _as_api(connection, a)
        stored = await connection.execute(
            text("UPDATE queue_item SET requested_by = :d WHERE id = :i"), {"d": device, "i": item}
        )
        assert stored.rowcount == 1

    count = text("SELECT count(*) FROM queue_item WHERE requested_by = :d")
    # …y desde B, con RLS, esa canción no existe.
    async with engine.begin() as connection:
        await _as_api(connection, b)
        assert (await connection.execute(count, {"d": device})).scalar_one() == 0
    async with engine.begin() as connection:
        await _as_api(connection, a)
        assert (await connection.execute(count, {"d": device})).scalar_one() == 1


def _queue_item_columns_and_indexes(database_url: str) -> set[str]:
    async def query() -> set[str]:
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as connection:
                rows = await connection.execute(
                    text(
                        "SELECT 'column:' || column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'queue_item' "
                        "UNION ALL "
                        "SELECT 'index:' || indexname FROM pg_indexes "
                        "WHERE schemaname = 'public' AND tablename = 'queue_item'"
                    )
                )
                return set(rows.scalars())
        finally:
            await engine.dispose()

    return asyncio.run(query())


def test_migracion_0003_baja_a_0002_y_sube(database_url: str) -> None:
    config = alembic_config(database_url)
    added = {"column:requested_by", "index:queue_item_pending_by_device_idx"}

    command.downgrade(config, "0002_music_sessions")
    objects = _queue_item_columns_and_indexes(database_url)
    assert not added & objects
    assert "column:track_ref" in objects

    command.upgrade(config, "head")
    assert added <= _queue_item_columns_and_indexes(database_url)
