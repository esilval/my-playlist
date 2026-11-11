"""Las migraciones con un usuario como el maestro de RDS (feature 004, plan D5, D8).

En RDS, el usuario maestro tiene CREATEROLE y CREATEDB y es dueño de la base, pero no es
superusuario. Se imita con un usuario así en el PostgreSQL del compose, en una base nueva.

Los roles `app_*` son de todo el servidor, y en el compose ya existen, creados por un
superusuario. En RDS los crearía el maestro, y por eso tendría ADMIN sobre ellos: la
prueba se lo da antes de migrar.
"""

import asyncio
from collections.abc import Iterator
from uuid import uuid4

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration.conftest import alembic_config

APP_ROLES = ("app_migrator", "app_api", "app_worker")


def _run(database_url: str, *statements: str, database: str = "postgres") -> list[object]:
    async def go() -> list[object]:
        url = make_url(database_url).set(database=database)
        engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as connection:
                results: list[object] = []
                for statement in statements:
                    result = await connection.execute(text(statement))
                    results.append(result.scalar() if result.returns_rows else None)
                return results
        finally:
            await engine.dispose()

    return asyncio.run(go())


@pytest.fixture
def rds_like(database_url: str) -> Iterator[tuple[str, str]]:
    """Un usuario como el maestro de RDS y una base nueva suya: devuelve su URL y la base."""
    suffix = uuid4().hex[:8]
    user, database = f"rds_like_{suffix}", f"rds_like_{suffix}"
    _run(
        database_url,
        f"CREATE ROLE {user} LOGIN CREATEROLE CREATEDB NOSUPERUSER PASSWORD 'clave-maestra'",
        f"CREATE DATABASE {database} OWNER {user}",
        *(f"GRANT {role} TO {user} WITH ADMIN OPTION" for role in APP_ROLES),
    )
    url = make_url(database_url).set(username=user, password="clave-maestra", database=database)
    try:
        yield url.render_as_string(hide_password=False), database
    finally:
        _run(
            database_url,
            f"DROP DATABASE IF EXISTS {database} WITH (FORCE)",
            *(f"REVOKE {role} FROM {user} CASCADE" for role in APP_ROLES),
            f"DROP ROLE IF EXISTS {user}",
        )


def _bypass(database_url: str) -> dict[str, object]:
    values = _run(
        database_url,
        *(f"SELECT rolbypassrls FROM pg_roles WHERE rolname = '{role}'" for role in APP_ROLES),
    )
    return dict(zip(APP_ROLES, values, strict=True))


def test_F004_R004_las_migraciones_corren_en_una_base_nueva_con_un_usuario_createrole_sin_superusuario(  # noqa: E501
    database_url: str, rds_like: tuple[str, str]
) -> None:
    url, database = rds_like

    command.upgrade(alembic_config(url), "head")

    head = ScriptDirectory.from_config(alembic_config(url)).get_current_head()
    [version] = _run(database_url, "SELECT version_num FROM alembic_version", database=database)
    assert version == head
    assert _bypass(database_url) == dict.fromkeys(APP_ROLES, False)
    # Las tablas son de app_migrator, no del usuario que migró.
    [owner] = _run(
        database_url,
        "SELECT tableowner FROM pg_tables WHERE tablename = 'music_session'",
        database=database,
    )
    assert owner == "app_migrator"


def test_F004_R004_la_0001_corrige_un_rol_app_que_ya_tenia_bypassrls(database_url: str) -> None:
    database = f"bypass_{uuid4().hex[:8]}"
    _run(database_url, f"CREATE DATABASE {database}", "ALTER ROLE app_worker BYPASSRLS")
    url = make_url(database_url).set(database=database).render_as_string(hide_password=False)
    try:
        assert _bypass(database_url)["app_worker"] is True

        command.upgrade(alembic_config(url), "head")

        assert _bypass(database_url) == dict.fromkeys(APP_ROLES, False)
    finally:
        _run(
            database_url,
            "ALTER ROLE app_worker NOBYPASSRLS",
            f"DROP DATABASE IF EXISTS {database} WITH (FORCE)",
        )
