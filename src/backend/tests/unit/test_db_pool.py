"""El pool de conexiones de la API es fijo (feature 003, plan D11)."""

import pytest
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.shared.db import POOL_SIZE, Database

pytestmark = pytest.mark.anyio


async def test_F003_R003_el_pool_de_la_api_es_fijo_sin_desborde() -> None:
    db = Database.from_url("postgresql+asyncpg://u:p@localhost:5432/db", role="app_api")
    try:
        pool = db._engine.pool
        assert isinstance(pool, AsyncAdaptedQueuePool)
        # 15 conexiones que se reutilizan; ninguna de desborde que se abra y se cierre.
        assert (pool.size(), pool._max_overflow) == (POOL_SIZE, 0) == (15, 0)
        assert pool._pre_ping is True
    finally:
        await db.dispose()
