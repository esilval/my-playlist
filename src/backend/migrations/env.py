"""Entorno de Alembic con motor asíncrono (ADR-0013)."""

import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.shared.config import get_settings

config = context.config


def _database_url() -> str:
    # Las pruebas pasan la URL de su base de datos con `sqlalchemy.url`.
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def _run(connection: Connection) -> None:
    context.configure(connection=connection, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine(_database_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Las migraciones solo se ejecutan en modo online.")

asyncio.run(_run_async())
