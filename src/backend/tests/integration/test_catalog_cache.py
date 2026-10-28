"""Caché del catálogo y límite de búsquedas contra el Redis real de docker-compose
(plan D2)."""

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis

from app.catalog.application.search import (
    SEARCHES_PER_MINUTE,
    SearchRateExceeded,
    SearchTracks,
    TrackLookup,
)
from app.catalog.domain.catalog import CatalogTrack, CatalogUnavailable
from app.catalog.infrastructure.cache import RedisCatalogCache
from app.catalog.infrastructure.fake import FakeCatalog
from app.shared.config import get_settings

pytestmark = pytest.mark.anyio


class CountingCatalog:
    """El catálogo falso, contando las veces que se pregunta al proveedor."""

    def __init__(self) -> None:
        self.fake = FakeCatalog()
        self.searches = 0
        self.lookups = 0

    async def search(self, query: str, limit: int) -> list[CatalogTrack]:
        self.searches += 1
        return await self.fake.search(query, limit)

    async def lookup(self, ref: str) -> CatalogTrack | None:
        self.lookups += 1
        return await self.fake.lookup(ref)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url(get_settings().redis_url)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def cache() -> AsyncIterator[RedisCatalogCache]:
    cache = RedisCatalogCache.from_url(get_settings().redis_url)
    try:
        yield cache
    finally:
        await cache.aclose()


async def _keys(redis: Redis, establishment_id: UUID) -> list[str]:
    return [key.decode() async for key in redis.scan_iter(match=f"*{establishment_id}*")]


async def test_F003_R003_una_busqueda_repetida_sale_de_la_cache(
    cache: RedisCatalogCache, redis: Redis
) -> None:
    catalog = CountingCatalog()
    search = SearchTracks(catalog=catalog, cache=cache)
    establishment, device = uuid4(), uuid4()

    first = await search(establishment, device, "Café  Tacvba")
    # Otra forma de escribir lo mismo: sin tildes, otras mayúsculas y otros espacios.
    again = await search(establishment, uuid4(), "cafe tacvba ")

    assert again == first
    assert catalog.searches == 1
    # La caché es de cada establecimiento: otro vuelve a preguntar al proveedor.
    await search(uuid4(), device, "Café Tacvba")
    assert catalog.searches == 2

    # Todas las claves llevan el prefijo del establecimiento (S8). La de la búsqueda es un
    # hash: no lleva el texto buscado.
    keys = await _keys(redis, establishment)
    assert all(key.startswith(f"est:{establishment}:") for key in keys)
    [search_key] = [key for key in keys if ":catalog:search:" in key]
    assert "tacvba" not in search_key.lower()
    assert len(search_key.rsplit(":", 1)[1]) == 64


async def test_F003_R014_lookup_siempre_pregunta_al_proveedor_aunque_se_haya_buscado(
    cache: RedisCatalogCache, redis: Redis
) -> None:
    catalog = CountingCatalog()
    establishment = uuid4()
    lookup = TrackLookup(catalog=catalog)

    # Una canción que salió en una búsqueda se consulta igual al pedirla.
    [found, *_] = await SearchTracks(catalog=catalog, cache=cache)(establishment, uuid4(), "rock")
    assert await lookup(establishment, found.ref) == found
    assert catalog.lookups == 1

    # Si dejó de existir después de la búsqueda, el pedido se rechaza (R014).
    [retired, *_] = await SearchTracks(catalog=catalog, cache=cache)(
        establishment, uuid4(), "retirada"
    )
    assert await lookup(establishment, retired.ref) is None
    assert catalog.lookups == 2

    # Ninguna canción suelta queda en la caché: solo las búsquedas.
    catalog_keys = [key for key in await _keys(redis, establishment) if ":catalog:" in key]
    assert len(catalog_keys) == 2
    assert all(":catalog:search:" in key for key in catalog_keys)


async def test_F003_R013_la_busqueda_11_en_un_minuto_lanza_search_rate_exceeded(
    cache: RedisCatalogCache, redis: Redis
) -> None:
    search = SearchTracks(catalog=CountingCatalog(), cache=cache)
    establishment, device = uuid4(), uuid4()

    # También cuentan las que salen de la caché.
    for _ in range(SEARCHES_PER_MINUTE):
        await search(establishment, device, "rock")

    with pytest.raises(SearchRateExceeded) as raised:
        await search(establishment, device, "rock")
    assert 1 <= raised.value.retry_after <= 60
    # La ventana es de un minuto desde la primera búsqueda: al pasar, el límite se levanta.
    ttl = await redis.ttl(f"est:{establishment}:search-rate:{device}")
    assert 0 < ttl <= 60
    # Otro dispositivo, u otro establecimiento, sigue pudiendo buscar.
    await search(establishment, uuid4(), "rock")
    await search(uuid4(), device, "rock")
    assert SEARCHES_PER_MINUTE == 10


async def test_F003_R013_sin_redis_la_busqueda_sigue() -> None:
    # Un Redis que no responde: nada escucha en ese puerto.
    cache = RedisCatalogCache.from_url("redis://127.0.0.1:1/0")
    catalog = CountingCatalog()
    search = SearchTracks(catalog=catalog, cache=cache)
    establishment, device = uuid4(), uuid4()
    try:
        # Sin caché ni límite: cada búsqueda va al proveedor, también pasadas las 10.
        for _ in range(SEARCHES_PER_MINUTE + 1):
            assert len(await search(establishment, device, "rock")) == 5
        assert catalog.searches == SEARCHES_PER_MINUTE + 1
        found = await TrackLookup(catalog=catalog)(establishment, "fake:rock-1")
        assert found is not None
    finally:
        await cache.aclose()


async def test_F003_R012_catalog_unavailable_llega_sin_cachear_nada(
    cache: RedisCatalogCache, redis: Redis
) -> None:
    catalog = CountingCatalog()
    search = SearchTracks(catalog=catalog, cache=cache)
    establishment = uuid4()

    for _ in range(2):
        with pytest.raises(CatalogUnavailable):
            await search(establishment, uuid4(), "caído")

    # Las dos veces se preguntó al proveedor: el fallo no se guarda.
    assert catalog.searches == 2
    assert not [key for key in await _keys(redis, establishment) if ":catalog:" in key]


async def test_F003_R003_una_entrada_corrupta_de_la_cache_no_rompe_la_busqueda(
    cache: RedisCatalogCache, redis: Redis
) -> None:
    catalog = CountingCatalog()
    search = SearchTracks(catalog=catalog, cache=cache)
    establishment = uuid4()
    await search(establishment, uuid4(), "rock")
    [key] = [key for key in await _keys(redis, establishment) if ":catalog:search:" in key]
    for broken in ("no es json", '[{"ref": "fake:rock-1"}]', '{"otro": "formato"}'):
        await redis.set(key, broken)

        assert len(await search(establishment, uuid4(), "rock")) == 5
    # Cada vez que no se entendía, se volvió a preguntar al proveedor.
    assert catalog.searches == 4
