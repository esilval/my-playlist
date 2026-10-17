"""Base de datos real de pruebas (ADR-0013: nunca SQLite).

Se crea una base `<nombre>_test` en el PostgreSQL de DATABASE_URL, se migra a
`head` una vez por sesión y cada prueba deja las tablas vacías al terminar.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.shared.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _test_url() -> str:
    url = make_url(get_settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


async def _recreate_database(test_url: str) -> None:
    url = make_url(test_url)
    admin = create_async_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
            await connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        await admin.dispose()


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    url = _test_url()
    asyncio.run(_recreate_database(url))
    command.upgrade(alembic_config(url), "head")
    yield url


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("TRUNCATE establishment, login_attempt RESTART IDENTITY CASCADE")
            )
        await engine.dispose()
