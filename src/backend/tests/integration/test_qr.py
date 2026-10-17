import io
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import httpx2
import pytest
import zxingcpp
from PIL import Image, ImageChops
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.accounts.infrastructure.qr_image import SegnoQrImageRenderer
from tests.integration.api import PUBLIC_BASE_URL, api_client, build_app_with_probe, register

pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
QR_URL = "/api/owner/establishment/qr.png"


@dataclass
class Ctx:
    client: httpx2.AsyncClient
    engine: AsyncEngine


@pytest.fixture
async def ctx(engine: AsyncEngine, database_url: str) -> AsyncIterator[Ctx]:
    async with api_client(build_app_with_probe(database_url)) as client:
        await register(client, "a@ejemplo.com", "contraseña-segura", "Bar La Esquina")
        login = await client.post(
            "/api/auth/login", json={"email": "a@ejemplo.com", "password": "contraseña-segura"}
        )
        assert login.status_code == 200
        yield Ctx(client=client, engine=engine)


async def _verify_email(ctx: Ctx) -> None:
    async with ctx.engine.begin() as connection:
        await connection.execute(text("UPDATE owner_account SET email_verified_at = now()"))


async def _public_code(ctx: Ctx) -> str:
    async with ctx.engine.connect() as connection:
        code: str = (
            await connection.execute(text("SELECT public_code FROM establishment"))
        ).scalar_one()
    return code


def _decode(png: bytes) -> list[str]:
    return [result.text for result in zxingcpp.read_barcodes(Image.open(io.BytesIO(png)))]


async def test_F001_R010_png_decodifica_a_la_url_publica(ctx: Ctx) -> None:
    await _verify_email(ctx)

    response = await ctx.client.get(QR_URL)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store"
    assert _decode(response.content) == [f"{PUBLIC_BASE_URL}/l/{await _public_code(ctx)}"]
    image = Image.open(io.BytesIO(response.content))
    assert image.width == 1200 and image.height > image.width  # QR con el nombre debajo


TEXT_STRIP = 220  # alto de la franja del nombre, al pie de la imagen


def _changed(a: Image.Image, b: Image.Image) -> int:
    """Píxeles que difieren en más de 32 niveles de gris."""
    return sum(ImageChops.difference(a, b).histogram()[33:])


def _composition_matches(rendered: Image.Image, reference: Image.Image) -> bool:
    if rendered.size != reference.size:
        return False
    split = reference.height - TEXT_STRIP
    top = (0, 0, reference.width, split)
    strip = (0, split, reference.width, reference.height)
    # El texto se compara aparte y casi exacto: quitar una sola tilde cambia ~75 píxeles.
    return (
        _changed(rendered.crop(top), reference.crop(top)) <= reference.width * split // 1000
        and _changed(rendered.crop(strip), reference.crop(strip)) <= 20
    )


def _render(name: str) -> Image.Image:
    png = SegnoQrImageRenderer().render(f"{PUBLIC_BASE_URL}/l/ABCDEFGHJK", name)
    return Image.open(io.BytesIO(png)).convert("L")


def test_F001_R010_composicion_incluye_nombre_con_tildes() -> None:
    # Referencia generada con esta misma composición y la fuente Inter empaquetada.
    reference = Image.open(FIXTURES / "qr_cafe_nandu.png").convert("L")

    assert _composition_matches(_render("Café Ñandú"), reference)
    # La comparación es sensible: sin tildes o sin la eñe ya no coincide.
    for altered in ("Cafe Ñandú", "Café Nandú", "Café Ñandu"):
        assert not _composition_matches(_render(altered), reference), altered


async def test_F001_R010_download_envia_content_disposition(ctx: Ctx) -> None:
    await _verify_email(ctx)

    response = await ctx.client.get(QR_URL, params={"download": "1"})

    assert response.status_code == 200
    expected = f'attachment; filename="qr-{await _public_code(ctx)}.png"'
    assert response.headers["content-disposition"] == expected
    assert "content-disposition" not in (await ctx.client.get(QR_URL)).headers


async def test_F001_R018_correo_sin_verificar_da_403_email_not_verified(ctx: Ctx) -> None:
    for params in ({}, {"download": "1"}):
        response = await ctx.client.get(QR_URL, params=params)

        assert response.status_code == 403
        assert response.json() == {"error": "email_not_verified"}
        assert response.headers["content-type"] == "application/json"


async def test_F001_R009_qr_igual_tras_cambiar_nombre(ctx: Ctx) -> None:
    await _verify_email(ctx)
    first = await ctx.client.get(QR_URL)
    assert first.status_code == 200
    before = _decode(first.content)
    assert before == [f"{PUBLIC_BASE_URL}/l/{await _public_code(ctx)}"]

    assert (
        await ctx.client.patch("/api/owner/establishment", json={"name": "La Esquina Bar"})
    ).status_code == 200
    second = await ctx.client.get(QR_URL)
    assert second.status_code == 200
    after = _decode(second.content)

    assert before == after


async def test_F001_R015_qr_sin_sesion_da_401(ctx: Ctx) -> None:
    ctx.client.cookies.clear()

    assert (await ctx.client.get(QR_URL)).status_code == 401
