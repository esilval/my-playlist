"""Usuarios de conexión de los servicios: `python -m app.ops.db_users` (feature 004, D5).

Corre en la tarea de migración, con el usuario maestro de RDS y después de
`alembic upgrade head`. Deja dos usuarios con contraseña:

- `myplaylist_api`, miembro de `app_api`;
- `myplaylist_worker`, miembro de `app_worker`.

Ninguno puede saltarse RLS, crear roles, ser superusuario ni migrar: no tienen
`BYPASSRLS` ni `CREATEROLE`, y no son miembros de `app_migrator` ni de `rds_superuser`
(constitución, «Base de datos»). Es idempotente: cada despliegue asigna la contraseña que
lee del entorno, así que cambiarla es cambiar el secreto y volver a desplegar.

Los atributos que solo un superusuario puede cambiar (`BYPASSRLS`, `SUPERUSER`,
`REPLICATION`) no se nombran: un rol nuevo nace sin ellos, y si alguno los tuviera, la
comprobación final falla y el despliegue se detiene (D8).
"""

import asyncio
import base64
import hashlib
import hmac
import os
import secrets
import sys
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.ops.env import compose_urls


@dataclass(frozen=True)
class ServiceUser:
    name: str
    role: str
    password_variable: str


SERVICE_USERS = (
    ServiceUser("myplaylist_api", "app_api", "DATABASE_API_PASSWORD"),
    ServiceUser("myplaylist_worker", "app_worker", "DATABASE_WORKER_PASSWORD"),
)
# Ninguno de estos puede estar entre los roles de un usuario de servicio.
FORBIDDEN_MEMBERSHIPS = ("app_migrator", "rds_superuser")


class UnsafeServiceUser(Exception):
    """Un usuario de servicio tiene un privilegio que no debe tener."""


SCRAM_ITERATIONS = 4096


def scram_verifier(password: str, salt: bytes | None = None) -> str:
    """El verificador SCRAM-SHA-256 de una contraseña, en el formato que guarda
    PostgreSQL (RFC 5802 y RFC 7677). Así la contraseña en claro no llega al servidor: ni
    a su registro si la sentencia falla, ni a `log_statement` ni a `pg_stat_statements`.

    PostgreSQL normaliza la contraseña con SASLprep. Aquí se usa NFKC, que coincide con
    ella para las contraseñas que generamos (ASCII) y para los textos habituales."""
    salt = salt if salt is not None else secrets.token_bytes(16)
    normalized = unicodedata.normalize("NFKC", password).encode()
    salted = hashlib.pbkdf2_hmac("sha256", normalized, salt, SCRAM_ITERATIONS)
    client_key = hmac.digest(salted, b"Client Key", "sha256")
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.digest(salted, b"Server Key", "sha256")

    def b64(value: bytes) -> str:
        return base64.b64encode(value).decode()

    return f"SCRAM-SHA-256${SCRAM_ITERATIONS}:{b64(salt)}${b64(stored_key)}:{b64(server_key)}"


class ServiceUserError(Exception):
    """No se pudo crear o cambiar un usuario de servicio. El mensaje no repite la
    sentencia, que lleva la contraseña."""


async def _execute_formatted(
    connection: AsyncConnection, template: str, *arguments: str, secret: bool = False
) -> None:
    """Ejecuta una sentencia DDL con nombres y literales escapados por PostgreSQL
    (`format` con `%I` y `%L`): el DDL no admite parámetros. Con `secret`, la sentencia
    lleva una contraseña, y un error no la repite."""
    placeholders = ", ".join(f"CAST(:a{index} AS text)" for index in range(len(arguments)))
    statement = (
        await connection.execute(
            text(f"SELECT format(CAST(:template AS text), {placeholders})"),
            {"template": template, **{f"a{i}": value for i, value in enumerate(arguments)}},
        )
    ).scalar_one()
    # Tal cual al controlador: el verificador SCRAM lleva «:», que text() tomaría por un
    # parámetro.
    if not secret:
        await connection.exec_driver_sql(statement)
        return
    try:
        await connection.exec_driver_sql(statement)
    except DBAPIError as error:
        command = template.split(" %")[0]
        raise ServiceUserError(f"{command} falló: {type(error.orig).__name__}") from None


async def ensure_service_user(
    connection: AsyncConnection, user: ServiceUser, password: str
) -> None:
    if not password:
        raise ValueError(f"falta la contraseña de {user.name}: {user.password_variable}")
    exists = (
        await connection.execute(
            text("SELECT EXISTS (SELECT FROM pg_roles WHERE rolname = :n)"), {"n": user.name}
        )
    ).scalar_one()
    verifier = scram_verifier(password)
    if exists:
        await _execute_formatted(
            connection,
            "ALTER ROLE %I LOGIN NOCREATEDB NOCREATEROLE PASSWORD %L",
            user.name,
            verifier,
            secret=True,
        )
    else:
        await _execute_formatted(
            connection,
            "CREATE ROLE %I LOGIN NOCREATEDB NOCREATEROLE PASSWORD %L",
            user.name,
            verifier,
            secret=True,
        )
    await _execute_formatted(connection, "GRANT %I TO %I", user.role, user.name)
    for forbidden in FORBIDDEN_MEMBERSHIPS:
        if await _is_member(connection, user.name, forbidden):
            await _execute_formatted(connection, "REVOKE %I FROM %I", forbidden, user.name)
    await check_service_user(connection, user)


async def _is_member(connection: AsyncConnection, member: str, role: str) -> bool:
    """Si `member` es miembro de `role`, directamente o a través de otros roles."""
    return bool(
        (
            await connection.execute(
                text(
                    # Sin el rol (rds_superuser fuera de RDS), pg_has_role daría error.
                    "SELECT CASE WHEN EXISTS (SELECT FROM pg_roles WHERE rolname = :role) "
                    "THEN pg_has_role(:member, :role, 'MEMBER') ELSE false END"
                ),
                {"member": member, "role": role},
            )
        ).scalar_one()
    )


async def check_service_user(connection: AsyncConnection, user: ServiceUser) -> None:
    row = (
        (
            await connection.execute(
                text(
                    "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolreplication, "
                    "rolcanlogin "
                    "FROM pg_roles WHERE rolname = :n"
                ),
                {"n": user.name},
            )
        )
        .mappings()
        .one()
    )
    problems = [
        attribute
        for attribute in (
            "rolsuper",
            "rolbypassrls",
            "rolcreaterole",
            "rolcreatedb",
            "rolreplication",
        )
        if row[attribute]
    ]
    if not row["rolcanlogin"]:
        problems.append("sin LOGIN")
    for forbidden in FORBIDDEN_MEMBERSHIPS:
        if await _is_member(connection, user.name, forbidden):
            problems.append(f"miembro de {forbidden}")
    if not await _is_member(connection, user.name, user.role):
        problems.append(f"no es miembro de {user.role}")
    if problems:
        raise UnsafeServiceUser(f"{user.name}: {', '.join(problems)}")


async def ensure_service_users(database_url: str, passwords: Mapping[str, str]) -> None:
    # Un error de SQLAlchemy repite los parámetros de la sentencia, y aquí llevan las
    # contraseñas: con hide_parameters no salen en ningún mensaje (R006).
    engine = create_async_engine(database_url, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            for user in SERVICE_USERS:
                await ensure_service_user(connection, user, passwords.get(user.name, ""))
    finally:
        await engine.dispose()


def main(environ: Mapping[str, str] = os.environ) -> int:
    database_url = compose_urls(environ).get("DATABASE_URL") or environ.get("DATABASE_URL", "")
    passwords = {user.name: environ.get(user.password_variable, "") for user in SERVICE_USERS}
    try:
        asyncio.run(ensure_service_users(database_url, passwords))
    except (ValueError, UnsafeServiceUser, ServiceUserError) as error:
        sys.stderr.write(f"usuarios de la base de datos: {error}\n")
        return 1
    sys.stdout.write(
        "usuarios de la base de datos listos: "
        + ", ".join(user.name for user in SERVICE_USERS)
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
