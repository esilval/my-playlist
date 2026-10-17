import hashlib
import urllib.parse
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.accounts.domain.data_policy import DRAFT_VERSION
from app.accounts.domain.ports import AccountRef
from app.accounts.infrastructure.argon2_hasher import Argon2PasswordHasher
from app.accounts.infrastructure.repositories import SqlAccountsRepository
from app.main import create_app
from app.shared.config import Settings
from app.shared.db import Database
from tests.integration.api import api_client, api_settings

pytestmark = pytest.mark.anyio


@dataclass
class Ctx:
    client: httpx2.AsyncClient
    engine: AsyncEngine  # superusuario, para comprobar sin RLS
    settings: Settings


@pytest.fixture
async def ctx(engine: AsyncEngine, database_url: str) -> AsyncIterator[Ctx]:
    settings = api_settings(database_url)
    async with api_client(create_app(settings)) as client:
        yield Ctx(client=client, engine=engine, settings=settings)


def _form(**overrides: Any) -> dict[str, Any]:
    form: dict[str, Any] = {
        "email": "Dueno@Ejemplo.com",
        "password": "contraseña-segura",
        "establishment_name": "Bar La Esquina",
        "data_authorization": True,
        "policy_version": DRAFT_VERSION,
    }
    form.update(overrides)
    return form


async def _rows(ctx: Ctx, sql: str) -> list[dict[str, Any]]:
    async with ctx.engine.connect() as connection:
        return [dict(row._mapping) for row in await connection.execute(text(sql))]


async def _count(ctx: Ctx, table: str) -> int:
    return int((await _rows(ctx, f"SELECT count(*) AS n FROM {table}"))[0]["n"])


async def _nothing_created(ctx: Ctx) -> bool:
    tables = ("establishment", "owner_account", "data_authorization", "email_token", "email_outbox")
    return all([await _count(ctx, table) == 0 for table in tables])


async def test_F001_R023_registro_crea_cuenta_y_establecimiento_sin_sesion(ctx: Ctx) -> None:
    response = await ctx.client.post("/api/auth/register", json=_form())

    assert response.status_code == 202
    assert response.json() == {"status": "check_email"}
    assert "set-cookie" not in response.headers
    assert await _count(ctx, "owner_session") == 0

    [account] = await _rows(ctx, "SELECT * FROM owner_account")
    [establishment] = await _rows(ctx, "SELECT * FROM establishment")
    assert (account["email"], account["email_normalized"]) == (
        "Dueno@Ejemplo.com",
        "dueno@ejemplo.com",
    )
    assert account["establishment_id"] == establishment["id"]
    assert establishment["name"] == "Bar La Esquina"
    assert account["email_verified_at"] is None


async def test_F001_R009_registro_asigna_codigo_publico(ctx: Ctx) -> None:
    await ctx.client.post("/api/auth/register", json=_form())
    await ctx.client.post("/api/auth/register", json=_form(email="otro@ejemplo.com"))

    codes = [
        row["public_code"] for row in await _rows(ctx, "SELECT public_code FROM establishment")
    ]
    assert len(codes) == 2 and len(set(codes)) == 2
    assert all(len(code) == 10 for code in codes)


async def test_F001_R023_credenciales_guardadas_permiten_autenticarse(ctx: Ctx) -> None:
    await ctx.client.post("/api/auth/register", json=_form())
    api = Database(ctx.engine, role="app_api")

    async with api.transaction() as connection:
        found = (
            await connection.execute(
                text("SELECT * FROM auth_account_by_email(:e)"), {"e": " DUENO@ejemplo.com "}
            )
        ).one()

    hasher = Argon2PasswordHasher.from_settings(ctx.settings)
    assert hasher.verify(found.password_hash, "contraseña-segura") is True
    assert hasher.verify(found.password_hash, "otra-contraseña") is False
    assert found.email_verified is False


async def test_F001_R023_direccion_y_telefono_opcionales(ctx: Ctx) -> None:
    with_contact = _form(address=" Calle 1 # 2-3 ", phone="3001234567")
    await ctx.client.post("/api/auth/register", json=with_contact)
    response = await ctx.client.post(
        "/api/auth/register", json=_form(email="sin@ejemplo.com", address="", phone=None)
    )

    assert response.status_code == 202
    rows = await _rows(ctx, "SELECT name, address, phone FROM establishment ORDER BY address")
    assert [(r["address"], r["phone"]) for r in rows] == [
        ("Calle 1 # 2-3", "3001234567"),
        (None, None),
    ]


async def test_F001_R003_422_con_errores_por_campo_sin_devolver_password(ctx: Ctx) -> None:
    form = _form(establishment_name="", email="sin-arroba", password="1234567")

    response = await ctx.client.post("/api/auth/register", json=form)

    assert response.status_code == 422
    assert response.json() == {
        "errors": {
            "establishment_name": "required",
            "email": "invalid_email",
            "password": "password_too_short",
        }
    }
    assert "1234567" not in response.text
    assert await _nothing_created(ctx)


async def test_F001_R004_sin_autorizacion_no_crea_cuenta(ctx: Ctx) -> None:
    response = await ctx.client.post("/api/auth/register", json=_form(data_authorization=False))

    assert response.status_code == 422
    assert response.json() == {"errors": {"data_authorization": "authorization_required"}}
    assert await _nothing_created(ctx)


async def test_F001_R022_guarda_version_y_fecha_de_la_autorizacion(ctx: Ctx) -> None:
    before = datetime.now(UTC)
    await ctx.client.post("/api/auth/register", json=_form())

    [authorization] = await _rows(ctx, "SELECT * FROM data_authorization")
    [account] = await _rows(ctx, "SELECT id, establishment_id FROM owner_account")
    assert authorization["policy_version"] == DRAFT_VERSION
    assert before <= authorization["granted_at"] <= datetime.now(UTC)
    assert (authorization["account_id"], authorization["establishment_id"]) == (
        account["id"],
        account["establishment_id"],
    )


async def test_F001_R022_version_desfasada_da_422(ctx: Ctx) -> None:
    response = await ctx.client.post("/api/auth/register", json=_form(policy_version="2025-01"))

    assert response.status_code == 422
    assert response.json() == {"errors": {"policy_version": "outdated"}}
    assert await _nothing_created(ctx)


async def test_F001_R017_registro_encola_correo_de_verificacion(ctx: Ctx) -> None:
    await ctx.client.post("/api/auth/register", json=_form())

    [message] = await _rows(ctx, "SELECT * FROM email_outbox")
    [token] = await _rows(ctx, "SELECT * FROM email_token")
    assert (message["template"], message["to_address"], message["status"]) == (
        "verify_email",
        "Dueno@Ejemplo.com",
        "pending",
    )
    assert message["payload"]["establishment_name"] == "Bar La Esquina"

    link = urllib.parse.urlsplit(message["payload"]["link"])
    assert (link.scheme, link.netloc, link.path) == ("https", "myplaylist.test", "/verificar")
    raw_token = urllib.parse.parse_qs(link.query)["token"][0]
    # En la base solo está el hash del token del enlace.
    assert token["token_hash"] == hashlib.sha256(raw_token.encode()).digest()
    assert token["purpose"] == "verify"
    assert token["used_at"] is None
    assert token["expires_at"] - token["created_at"] == timedelta(days=7)


async def test_F001_R022_privacidad_solo_guarda_los_datos_previstos(ctx: Ctx) -> None:
    password = "contraseña-segura"
    await ctx.client.post("/api/auth/register", json=_form(password=password))

    expected = {
        "owner_account": [
            "created_at",
            "email",
            "email_normalized",
            "email_verified_at",
            "establishment_id",
            "id",
            "password_hash",
        ],
        "establishment": [
            "address",
            "created_at",
            "establishment_id",
            "id",
            "name",
            "phone",
            "public_code",
            "updated_at",
        ],
        "data_authorization": [
            "account_id",
            "establishment_id",
            "granted_at",
            "id",
            "policy_version",
        ],
    }
    for table, columns in expected.items():
        rows = await _rows(
            ctx,
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' "
            f"AND table_name = '{table}' ORDER BY column_name",
        )
        assert [r["column_name"] for r in rows] == columns, table
    # La contraseña no aparece en claro en ninguna tabla.
    for table in (
        "establishment",
        "owner_account",
        "data_authorization",
        "email_token",
        "email_outbox",
    ):
        dump = await _rows(ctx, f"SELECT row_to_json(t)::text AS j FROM {table} t")
        assert all(password not in row["j"] for row in dump), table


async def test_F001_R003_tipos_incorrectos_dan_errores_sin_devolver_el_valor(ctx: Ctx) -> None:
    response = await ctx.client.post(
        "/api/auth/register", json=_form(password=12345678, data_authorization="quizá")
    )

    assert response.status_code == 422
    assert response.json() == {"errors": {"password": "invalid", "data_authorization": "invalid"}}
    assert "12345678" not in response.text
    assert await _nothing_created(ctx)


async def test_F001_R003_json_mal_formado_da_el_mismo_formato(ctx: Ctx) -> None:
    response = await ctx.client.post(
        "/api/auth/register",
        content=b'{"password": "secreto-123", ',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422
    assert set(response.json()) == {"errors"}
    assert "secreto-123" not in response.text


async def _snapshot(ctx: Ctx) -> dict[str, int]:
    tables = ("establishment", "owner_account", "data_authorization", "email_token")
    return {table: await _count(ctx, table) for table in tables}


async def test_F001_R024_correo_existente_con_mayusculas_no_crea_nada(ctx: Ctx) -> None:
    await ctx.client.post("/api/auth/register", json=_form(email="a@ejemplo.com"))
    before = await _snapshot(ctx)

    response = await ctx.client.post(
        "/api/auth/register",
        json=_form(email="A@Ejemplo.com", establishment_name="Otro bar", password="otra-clave-1"),
    )

    assert response.status_code == 202
    assert (
        await _snapshot(ctx)
        == before
        == {
            "establishment": 1,
            "owner_account": 1,
            "data_authorization": 1,
            "email_token": 1,
        }
    )
    [establishment] = await _rows(ctx, "SELECT name FROM establishment")
    assert establishment["name"] == "Bar La Esquina"


async def test_F001_R024_respuesta_identica_a_registro_nuevo(ctx: Ctx) -> None:
    new = await ctx.client.post("/api/auth/register", json=_form(email="a@ejemplo.com"))
    existing = await ctx.client.post("/api/auth/register", json=_form(email="A@Ejemplo.com"))

    assert existing.status_code == new.status_code == 202
    assert existing.content == new.content
    assert dict(existing.headers) == dict(new.headers)
    assert "set-cookie" not in existing.headers


async def test_F001_R024_encola_aviso_con_enlaces_a_entrar_y_recuperar(ctx: Ctx) -> None:
    await ctx.client.post("/api/auth/register", json=_form(email="a@ejemplo.com"))
    await ctx.client.post("/api/auth/register", json=_form(email=" A@Ejemplo.com"))

    [holder] = await _rows(ctx, "SELECT establishment_id FROM owner_account")
    [notice] = await _rows(
        ctx, "SELECT * FROM email_outbox WHERE template = 'registration_attempt'"
    )
    assert notice["establishment_id"] == holder["establishment_id"]
    assert notice["to_address"] == "a@ejemplo.com"  # la guardada, no la escrita
    assert notice["to_address_normalized"] == "a@ejemplo.com"
    assert notice["payload"] == {
        "login_link": "https://myplaylist.test/entrar",
        "reset_link": "https://myplaylist.test/recuperar",
    }


async def test_F001_R024_carrera_por_indice_unico_se_trata_como_existente(ctx: Ctx) -> None:
    await ctx.client.post("/api/auth/register", json=_form(email="a@ejemplo.com"))
    before = await _snapshot(ctx)

    # La primera búsqueda no ve la cuenta, como si el otro alta aún no estuviera confirmada.
    original = SqlAccountsRepository.find_owner_by_email
    calls: list[str] = []

    async def stale_once(self: SqlAccountsRepository, email_normalized: str) -> AccountRef | None:
        calls.append(email_normalized)
        if len(calls) == 1:
            return None
        return await original(self, email_normalized)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(SqlAccountsRepository, "find_owner_by_email", stale_once)
        response = await ctx.client.post("/api/auth/register", json=_form(email="a@ejemplo.com"))

    assert response.status_code == 202
    assert response.json() == {"status": "check_email"}
    assert len(calls) == 2
    # El alta fallida se deshizo entera: ni establecimiento huérfano ni token.
    assert await _snapshot(ctx) == before
    templates = await _rows(ctx, "SELECT template FROM email_outbox ORDER BY created_at")
    assert [t["template"] for t in templates] == ["verify_email", "registration_attempt"]
