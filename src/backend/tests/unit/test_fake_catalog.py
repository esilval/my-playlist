import pytest

from app.catalog.domain.catalog import CatalogTrack, CatalogUnavailable
from app.catalog.infrastructure.fake import FakeCatalog

pytestmark = pytest.mark.anyio


async def test_F003_R003_el_catalogo_falso_es_determinista_con_sus_textos_especiales() -> None:
    catalog = FakeCatalog()

    # Cinco canciones por defecto, siempre las mismas, que se reconocen al pedirlas.
    first = await catalog.search("Música Bailable", 10)
    assert first == await catalog.search("música bailable", 10)
    assert [track.ref for track in first] == [f"fake:musica-bailable-{n}" for n in range(1, 6)]
    assert first[0] == CatalogTrack(
        ref="fake:musica-bailable-1", title="Canción 1 de musica-bailable", author="Catálogo falso"
    )
    assert [await catalog.lookup(track.ref) for track in first] == first
    assert len(await catalog.search("otra", 2)) == 2

    # Textos especiales: una que falla al sonar, el proveedor caído, nada y una retirada.
    assert [track.ref for track in await catalog.search("error", 10)] == ["fake:error"]
    assert await catalog.lookup("fake:error") is not None
    with pytest.raises(CatalogUnavailable):
        await catalog.search("caído", 10)
    assert await catalog.search("nada", 10) == []
    [retired] = await catalog.search("retirada", 1)
    assert await catalog.lookup(retired.ref) is None

    # Una referencia que no es del catálogo falso no se reconoce.
    for ref in ("yt:AAAAAAAAAAA", "fake:", "fake:sin-numero-x"):
        assert await catalog.lookup(ref) is None
