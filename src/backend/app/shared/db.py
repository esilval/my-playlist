"""Unidad de trabajo con contexto de aislamiento (ADR-0009, plan D4).

Cada transacción adopta el rol sin BYPASSRLS de su proceso (`app_api` para la
API) y, cuando ya se conoce, fija el establecimiento con `SET LOCAL`. Ninguna
consulta de negocio corre fuera de una transacción con ese contexto: sin él,
las políticas RLS hacen fallar la consulta.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

DbRole = Literal["app_api", "app_worker"]

# Pool fijo por proceso (plan D11 de la feature 003): sin desborde, las conexiones se abren
# una vez y se reutilizan. Con desborde, cada pico abría y cerraba conexiones, y cada una
# nueva repetía la consulta con que asyncpg averigua los tipos propios de la base. Con 4
# procesos de la API (ADR-0015), el trabajador y la herramienta de desarrollo son como
# mucho 90 de las 100 conexiones de PostgreSQL en local.
POOL_SIZE = 15


async def set_establishment(connection: AsyncConnection, establishment_id: UUID) -> None:
    """Fija el establecimiento de la transacción en curso.

    El identificador sale siempre del servidor (sesión, token o una función
    SECURITY DEFINER), nunca de la entrada del cliente.
    """
    await connection.execute(
        text("SELECT set_config('app.establishment_id', :id, true)"),
        {"id": str(establishment_id)},
    )


class Database:
    def __init__(self, engine: AsyncEngine, role: DbRole) -> None:
        self._engine = engine
        self._role = role

    @classmethod
    def from_url(cls, url: str, role: DbRole) -> "Database":
        engine = create_async_engine(url, pool_size=POOL_SIZE, max_overflow=0, pool_pre_ping=True)
        return cls(engine, role)

    @asynccontextmanager
    async def transaction(
        self, establishment_id: UUID | None = None
    ) -> AsyncIterator[AsyncConnection]:
        async with self._engine.begin() as connection:
            # El nombre del rol viene de DbRole, no de la entrada del usuario.
            await connection.execute(text(f"SET LOCAL ROLE {self._role}"))
            if establishment_id is not None:
                await set_establishment(connection, establishment_id)
            yield connection

    async def dispose(self) -> None:
        await self._engine.dispose()
