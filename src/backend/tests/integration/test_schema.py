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


async def _create_establishment(
    connection: AsyncConnection, *, public_code: str, email: str
) -> uuid.UUID:
    establishment_id = uuid.uuid4()
    await connection.execute(
        text(
            "INSERT INTO establishment (id, establishment_id, public_code, name) "
            "VALUES (:id, :id, :code, 'Bar La Esquina')"
        ),
        {"id": establishment_id, "code": public_code},
    )
    await connection.execute(
        text(
            "INSERT INTO owner_account (establishment_id, email, email_normalized, password_hash) "
            "VALUES (:id, :email, lower(:email), 'hash')"
        ),
        {"id": establishment_id, "email": email},
    )
    return establishment_id


async def test_F001_R015_rls_oculta_filas_de_otro_establecimiento(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        a = await _create_establishment(connection, public_code="AAAAAAAAAA", email="a@ejemplo.com")
        b = await _create_establishment(connection, public_code="BBBBBBBBBB", email="b@ejemplo.com")

    async with engine.begin() as connection:
        await _as_api(connection, a)
        visible = await connection.execute(text("SELECT establishment_id FROM owner_account"))
        assert visible.scalars().all() == [a]

        hidden = await connection.execute(
            text("SELECT count(*) FROM establishment WHERE id = :b"), {"b": b}
        )
        assert hidden.scalar_one() == 0

        updated = await connection.execute(
            text("UPDATE establishment SET name = 'Hackeado' WHERE id = :b"), {"b": b}
        )
        assert updated.rowcount == 0


async def test_F001_R015_sin_contexto_la_consulta_falla(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        a = await _create_establishment(connection, public_code="AAAAAAAAAA", email="a@ejemplo.com")

    async with engine.connect() as connection:
        # Conexión que nunca fijó el contexto: el parámetro no existe.
        with pytest.raises(DBAPIError) as never_set:
            async with connection.begin():
                await connection.execute(text("SET LOCAL ROLE app_api"))
                await connection.execute(text("SELECT count(*) FROM establishment"))

        # Conexión reutilizada tras una transacción con contexto: queda vacío, no heredado.
        async with connection.begin():
            await _as_api(connection, a)
        with pytest.raises(DBAPIError) as left_empty:
            async with connection.begin():
                await connection.execute(text("SET LOCAL ROLE app_api"))
                await connection.execute(text("SELECT count(*) FROM establishment"))

    assert 'unrecognized configuration parameter "app.establishment_id"' in str(never_set.value)
    assert "invalid input syntax for type uuid" in str(left_empty.value)


async def test_F001_R015_no_inserta_en_otro_establecimiento(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        a = await _create_establishment(connection, public_code="AAAAAAAAAA", email="a@ejemplo.com")
        b = await _create_establishment(connection, public_code="BBBBBBBBBB", email="b@ejemplo.com")

    with pytest.raises(DBAPIError, match="row-level security"):
        async with engine.begin() as connection:
            await _as_api(connection, a)
            await connection.execute(
                text(
                    "INSERT INTO email_outbox (establishment_id, to_address, "
                    "to_address_normalized, template) "
                    "VALUES (:b, 'b@ejemplo.com', 'b@ejemplo.com', 'verify_email')"
                ),
                {"b": b},
            )

    async with engine.connect() as connection:
        written = await connection.execute(
            text("SELECT count(*) FROM email_outbox WHERE establishment_id = :b"), {"b": b}
        )
        assert written.scalar_one() == 0


async def test_F001_R009_public_code_no_se_puede_actualizar(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        a = await _create_establishment(connection, public_code="AAAAAAAAAA", email="a@ejemplo.com")

    with pytest.raises(IntegrityError, match="public_code es inmutable"):
        async with engine.begin() as connection:
            await _as_api(connection, a)
            await connection.execute(
                text("UPDATE establishment SET public_code = 'ZZZZZZZZZZ' WHERE id = :a"),
                {"a": a},
            )

    async with engine.begin() as connection:
        await _as_api(connection, a)
        await connection.execute(
            text("UPDATE establishment SET name = 'La Esquina Bar' WHERE id = :a"), {"a": a}
        )
        code = await connection.execute(text("SELECT public_code FROM establishment"))
        assert code.scalar_one() == "AAAAAAAAAA"


async def test_F001_R009_public_code_es_unico(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await _create_establishment(connection, public_code="AAAAAAAAAA", email="a@ejemplo.com")

    with pytest.raises(IntegrityError):
        async with engine.begin() as connection:
            await _create_establishment(connection, public_code="AAAAAAAAAA", email="b@ejemplo.com")


async def test_F001_R024_email_normalized_es_unico(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await _create_establishment(connection, public_code="AAAAAAAAAA", email="a@ejemplo.com")

    # La unicidad se aplica entre establecimientos, aunque RLS oculte la otra fila.
    with pytest.raises(IntegrityError, match="email_normalized"):
        async with engine.begin() as connection:
            await _create_establishment(connection, public_code="BBBBBBBBBB", email="A@Ejemplo.com")


async def test_toda_tabla_salvo_login_attempt_tiene_rls(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text(
                """
                SELECT c.relname, c.relrowsecurity,
                       EXISTS (SELECT FROM pg_policies p
                               WHERE p.schemaname = 'public' AND p.tablename = c.relname)
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                  AND c.relname <> 'alembic_version'
                """
            )
        )
        tables = {name: (rls, policy) for name, rls, policy in rows}

    assert tables.pop("login_attempt") == (False, False)
    assert tables, "la migración no creó tablas de negocio"
    assert {name for name, flags in tables.items() if flags != (True, True)} == set()


async def test_columnas_del_plan_existen(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public'"
            )
        )
        columns = {(table, column) for table, column in rows}
        index = await connection.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'email_outbox_quota_idx'")
        )
        quota_index = index.scalar_one()

    assert {
        ("data_authorization", "policy_version"),
        ("data_authorization", "granted_at"),
        ("email_token", "superseded_at"),
        ("email_token", "expires_at"),
        ("email_outbox", "to_address_normalized"),
    } <= columns
    assert "(establishment_id, to_address_normalized, template, created_at)" in quota_index


async def test_roles_de_la_api_y_el_trabajador_no_saltan_rls(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT rolname, rolbypassrls, rolcanlogin FROM pg_roles "
                "WHERE rolname IN ('app_api', 'app_worker', 'app_migrator')"
            )
        )
        roles = {name: (bypass, login) for name, bypass, login in rows}

    assert roles == {
        "app_api": (False, False),
        "app_worker": (False, False),
        "app_migrator": (False, False),
    }


def _schema_objects(database_url: str) -> set[str]:
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
                        UNION ALL
                        SELECT 'function:' || proname FROM pg_proc p
                          JOIN pg_namespace n ON n.oid = p.pronamespace
                         WHERE n.nspname = 'public'
                        """
                    )
                )
                return set(rows.scalars())
        finally:
            await engine.dispose()

    return asyncio.run(query())


def test_migracion_baja_y_sube(database_url: str) -> None:
    config = alembic_config(database_url)

    command.downgrade(config, "base")
    assert _schema_objects(database_url) == {"table:alembic_version"}

    command.upgrade(config, "head")
    assert {
        "table:establishment",
        "table:login_attempt",
        "type:email_template",
        "function:establishment_public_code_immutable",
    } <= _schema_objects(database_url)
