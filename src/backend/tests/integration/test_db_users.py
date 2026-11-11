"""Usuarios de conexión de los servicios contra el PostgreSQL real (feature 004, plan D5).

Los roles son de todo el servidor, no de una base: cada prueba borra al terminar los
usuarios que crea.
"""

import asyncio
import traceback
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.ops.db_users import SERVICE_USERS, UnsafeServiceUser, ensure_service_users

pytestmark = pytest.mark.anyio

PASSWORDS = {user.name: f"contraseña-de-{user.name}" for user in SERVICE_USERS}


async def _scalar(engine: AsyncEngine, sql: str, **params: object) -> object:
    async with engine.begin() as connection:
        return (await connection.execute(text(sql), params)).scalar_one()


@pytest.fixture
async def admin(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        async with engine.begin() as connection:
            for user in SERVICE_USERS:
                await connection.execute(text(f"DROP ROLE IF EXISTS {user.name}"))
        await engine.dispose()


def _as(database_url: str, user: str, password: str) -> AsyncEngine:
    url = make_url(database_url).set(username=user, password=password)
    return create_async_engine(url)


async def test_F004_R004_db_users_crea_api_y_worker_sin_bypassrls_createrole_ni_app_migrator(
    database_url: str, admin: AsyncEngine
) -> None:
    await ensure_service_users(database_url, PASSWORDS)

    for user in SERVICE_USERS:
        async with admin.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT rolcanlogin, rolsuper, rolbypassrls, rolcreaterole, "
                            "rolcreatedb, rolreplication, "
                            "pg_has_role(rolname, :role, 'MEMBER') AS in_role, "
                            "pg_has_role(rolname, 'app_migrator', 'MEMBER') AS migrator "
                            "FROM pg_roles WHERE rolname = :n"
                        ),
                        {"n": user.name, "role": user.role},
                    )
                )
                .mappings()
                .one()
            )
        assert dict(row) == {
            "rolcanlogin": True,
            "rolsuper": False,
            "rolbypassrls": False,
            "rolcreaterole": False,
            "rolcreatedb": False,
            "rolreplication": False,
            "in_role": True,
            "migrator": False,
        }, user.name


async def test_F004_R004_db_users_es_idempotente_y_cambia_la_contrasena(
    database_url: str, admin: AsyncEngine
) -> None:
    await ensure_service_users(database_url, PASSWORDS)
    # Alguien le da por error un rol de migración: el siguiente despliegue se lo quita.
    await _scalar(admin, "SELECT 1")
    async with admin.begin() as connection:
        await connection.execute(text("GRANT app_migrator TO myplaylist_api"))

    changed = {**PASSWORDS, "myplaylist_api": "contraseña-nueva-tras-rotar"}
    await ensure_service_users(database_url, changed)

    new = _as(database_url, "myplaylist_api", "contraseña-nueva-tras-rotar")
    old = _as(database_url, "myplaylist_api", PASSWORDS["myplaylist_api"])
    try:
        assert await _scalar(new, "SELECT current_user") == "myplaylist_api"
        with pytest.raises(DBAPIError):
            await _scalar(old, "SELECT 1")
    finally:
        await new.dispose()
        await old.dispose()
    assert (
        await _scalar(admin, "SELECT pg_has_role('myplaylist_api', 'app_migrator', 'MEMBER')")
        is False
    )

    # Un atributo que no puede quitar sin ser superusuario detiene el despliegue.
    async with admin.begin() as connection:
        await connection.execute(text("ALTER ROLE myplaylist_worker BYPASSRLS"))
    with pytest.raises(UnsafeServiceUser, match="myplaylist_worker: rolbypassrls"):
        await ensure_service_users(database_url, PASSWORDS)
    # Sin contraseña no crea nada.
    with pytest.raises(ValueError, match="DATABASE_API_PASSWORD"):
        await ensure_service_users(database_url, {})


def test_F004_R006_el_paso_de_despliegue_no_escribe_las_contrasenas(
    database_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """`python -m app.ops.db_users`, como lo corre la tarea de migración (D8)."""
    from app.ops.db_users import main

    env = {
        "DATABASE_URL": database_url,
        "DATABASE_API_PASSWORD": PASSWORDS["myplaylist_api"],
        "DATABASE_WORKER_PASSWORD": PASSWORDS["myplaylist_worker"],
    }
    try:
        assert main(env) == 0
        assert main({**env, "DATABASE_WORKER_PASSWORD": ""}) == 1
        output = capsys.readouterr()
        assert "DATABASE_WORKER_PASSWORD" in output.err
        for password in PASSWORDS.values():
            assert password not in output.out + output.err
    finally:

        async def _drop() -> None:
            engine = create_async_engine(database_url)
            async with engine.begin() as connection:
                for user in SERVICE_USERS:
                    await connection.execute(text(f"DROP ROLE IF EXISTS {user.name}"))
            await engine.dispose()

        asyncio.run(_drop())


async def test_F004_R006_una_sentencia_con_contrasena_que_falla_no_la_repite(
    database_url: str,
) -> None:
    from app.ops.db_users import ServiceUserError, _execute_formatted

    engine = create_async_engine(database_url, hide_parameters=True)
    try:
        with pytest.raises(ServiceUserError) as error:
            async with engine.begin() as connection:
                await _execute_formatted(
                    connection,
                    "ALTER ROLE %I LOGIN PASSWORD %L",
                    "rol_que_no_existe",
                    "contraseña-filtrable",
                    secret=True,
                )
    finally:
        await engine.dispose()
    assert "contraseña-filtrable" not in str(error.value)
    # `from None`: la traza no arrastra el error original, que lleva la sentencia.
    assert error.value.__suppress_context__ is True
    assert "contraseña-filtrable" not in "".join(traceback.format_exception(error.value))


async def test_F004_R006_la_contrasena_no_llega_en_claro_al_servidor(
    database_url: str, admin: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy.ext.asyncio import AsyncConnection

    from app.ops import db_users

    sent: list[str] = []
    original = AsyncConnection.exec_driver_sql

    async def spy(self: AsyncConnection, statement: str, *args: Any, **kwargs: Any) -> Any:
        sent.append(statement)
        return await original(self, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncConnection, "exec_driver_sql", spy)
    await db_users.ensure_service_users(database_url, PASSWORDS)
    monkeypatch.undo()

    role_statements = [statement for statement in sent if "ROLE" in statement]
    assert any("SCRAM-SHA-256$4096:" in statement for statement in role_statements)
    for password in PASSWORDS.values():
        assert all(password not in statement for statement in sent)
    # Y la contraseña sirve: el verificador es el que PostgreSQL espera.
    api = _as(database_url, "myplaylist_api", PASSWORDS["myplaylist_api"])
    try:
        assert await _scalar(api, "SELECT current_user") == "myplaylist_api"
    finally:
        await api.dispose()
