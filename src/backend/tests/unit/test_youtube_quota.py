"""Contador de la cuota diaria de YouTube (feature 004, R021, plan D11), sin red: Redis y
YouTube son de mentira."""

import logging
from datetime import UTC, datetime
from types import TracebackType
from typing import Any
from uuid import uuid4

import anyio
import httpx2
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.catalog.application.search import SearchTracks
from app.catalog.domain.catalog import CatalogTrack, CatalogUnavailable
from app.catalog.infrastructure.quota import (
    KEY_TTL_SECONDS,
    TIMEOUT_SECONDS,
    YouTubeQuotaCounter,
    quota_day,
    quota_key,
)
from app.catalog.infrastructure.youtube import YouTubeCatalog
from app.shared.metrics import InMemoryMetrics

pytestmark = pytest.mark.anyio

VIDEO = "AAAAAAAAAAA"
NOW = datetime(2026, 11, 11, 18, 0, tzinfo=UTC)


class FakeRedis:
    """Lo justo de Redis para el contador: una tubería con INCRBY y EXPIRE NX."""

    def __init__(self, *, fail: bool = False, delay: float = 0) -> None:
        self.values: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.fail = fail
        self.delay = delay

    def pipeline(self, transaction: bool = True) -> "FakePipeline":
        assert transaction
        return FakePipeline(self)

    async def aclose(self) -> None:
        pass


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._commands: list[tuple[str, str, int, bool]] = []

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(
        self, *_: type[BaseException] | BaseException | TracebackType | None
    ) -> None:
        pass

    def incrby(self, key: str, amount: int) -> None:
        self._commands.append(("incrby", key, amount, False))

    def expire(self, key: str, seconds: int, nx: bool = False) -> None:
        self._commands.append(("expire", key, seconds, nx))

    async def execute(self) -> list[Any]:
        if self._redis.delay:
            await anyio.sleep(self._redis.delay)
        if self._redis.fail:
            raise RedisConnectionError("Redis no responde")
        results: list[Any] = []
        for command, key, value, nx in self._commands:
            if command == "incrby":
                self._redis.values[key] = self._redis.values.get(key, 0) + value
                results.append(self._redis.values[key])
            else:
                assert nx
                set_now = key not in self._redis.ttls
                if set_now:
                    self._redis.ttls[key] = value
                results.append(set_now)
        return results


def _youtube_response(request: httpx2.Request) -> httpx2.Response:
    snippet = {"title": "Canción", "channelTitle": "Artista"}
    if request.url.path.endswith("/search"):
        return httpx2.Response(
            200, json={"items": [{"id": {"videoId": VIDEO}, "snippet": snippet}]}
        )
    return httpx2.Response(
        200, json={"items": [{"snippet": snippet, "status": {"embeddable": True}}]}
    )


def _setup(
    *, fail: bool = False, delay: float = 0, now: datetime = NOW
) -> tuple[YouTubeCatalog, FakeRedis, InMemoryMetrics, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def record(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return _youtube_response(request)

    redis = FakeRedis(fail=fail, delay=delay)
    metrics = InMemoryMetrics()
    counter = YouTubeQuotaCounter(redis, metrics, now=lambda: now)  # type: ignore[arg-type]
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(record))
    return YouTubeCatalog("clave", client, quota=counter), redis, metrics, seen


async def test_F004_R021_cada_search_suma_100_y_cada_videos_list_suma_1() -> None:
    catalog, redis, _, _ = _setup()

    await catalog.search("salsa", 10)
    await catalog.lookup(f"yt:{VIDEO}")
    await catalog.lookup(f"yt:{VIDEO}")
    await catalog.search("vallenato", 10)

    assert redis.values == {quota_key("2026-11-11"): 100 + 1 + 1 + 100}
    # Una referencia mal formada no llega a YouTube: no gasta cuota.
    assert await catalog.lookup("yt:corta") is None
    assert redis.values[quota_key("2026-11-11")] == 202


async def test_F004_R021_un_error_de_youtube_tambien_gasta_cuota() -> None:
    redis = FakeRedis()
    counter = YouTubeQuotaCounter(redis, InMemoryMetrics(), now=lambda: NOW)  # type: ignore[arg-type]
    client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(lambda _: httpx2.Response(403, json={}))
    )

    with pytest.raises(CatalogUnavailable):
        await YouTubeCatalog("clave", client, quota=counter).search("salsa", 10)

    assert redis.values == {quota_key("2026-11-11"): 100}


def test_F004_R021_el_dia_de_la_cuota_cambia_a_medianoche_del_pacifico() -> None:
    # Hora estándar del Pacífico (UTC-8).
    assert quota_day(datetime(2026, 11, 12, 7, 59, tzinfo=UTC)) == "2026-11-11"
    assert quota_day(datetime(2026, 11, 12, 8, 0, tzinfo=UTC)) == "2026-11-12"
    # Hora de verano (UTC-7).
    assert quota_day(datetime(2026, 7, 1, 6, 59, tzinfo=UTC)) == "2026-06-30"
    assert quota_day(datetime(2026, 7, 1, 7, 0, tzinfo=UTC)) == "2026-07-01"


async def test_F004_R021_emite_youtube_quota_used_con_el_total_del_dia() -> None:
    catalog, redis, metrics, _ = _setup()

    await catalog.search("salsa", 10)
    await catalog.lookup(f"yt:{VIDEO}")

    assert metrics.values("YouTubeQuotaUsed") == [100, 101]
    assert all(item.unit == "Count" and item.dimensions == {} for item in metrics.recorded)
    # La clave caduca a las 48 h, y solo se fija la primera vez.
    assert redis.ttls == {quota_key("2026-11-11"): KEY_TTL_SECONDS}

    # Al cambiar el día, empieza de cero.
    next_day, next_redis, next_metrics, _ = _setup(now=datetime(2026, 11, 12, 8, 0, tzinfo=UTC))
    next_redis.values = dict(redis.values)
    await next_day.search("salsa", 10)
    assert next_metrics.values("YouTubeQuotaUsed") == [100]
    assert next_redis.values[quota_key("2026-11-12")] == 100


class HitCache:
    """Caché que ya tiene la búsqueda guardada."""

    async def search(self, establishment_id: object, query_key: str) -> list[CatalogTrack]:
        return [CatalogTrack(ref=f"yt:{VIDEO}", title="Canción", author="Artista")]

    async def store_search(self, *_: object) -> None:
        raise AssertionError("una búsqueda de la caché no se vuelve a guardar")

    async def count_search(self, *_: object) -> tuple[int, int]:
        return 1, 60


async def test_F004_R021_la_busqueda_que_sale_de_la_cache_no_suma() -> None:
    catalog, redis, metrics, seen = _setup()
    search = SearchTracks(catalog=catalog, cache=HitCache())

    results = await search(uuid4(), uuid4(), "salsa")

    assert [track.title for track in results] == ["Canción"]
    assert seen == []
    assert redis.values == {}
    assert metrics.recorded == []


async def test_F004_R021_si_redis_falla_la_busqueda_sigue_y_queda_en_el_registro(
    caplog: pytest.LogCaptureFixture,
) -> None:
    catalog, _, metrics, _ = _setup(fail=True)

    with caplog.at_level(logging.WARNING, logger="app.catalog.infrastructure.quota"):
        results = await catalog.search("salsa", 10)

    assert [track.title for track in results] == ["Canción"]
    assert metrics.recorded == []
    assert "contador de cuota de YouTube sin respuesta" in caplog.text
    assert "salsa" not in caplog.text


async def test_F004_R021_un_redis_lento_no_retrasa_la_busqueda_mas_del_tope() -> None:
    catalog, redis, metrics, _ = _setup(delay=5)

    started = anyio.current_time()
    results = await catalog.search("salsa", 10)

    assert [track.title for track in results] == ["Canción"]
    assert anyio.current_time() - started < TIMEOUT_SECONDS + 0.3
    assert redis.values == {}
    assert metrics.recorded == []
