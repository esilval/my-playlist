"""Aislamiento entre establecimientos (R015, ADR-0009, S8).

Con dos establecimientos A y B y la sesión de A, nada de lo que A pueda hacer por
la API ni por la base de datos con el rol de la API le deja ver o cambiar a B.
"""

import io
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx2
import pytest
import zxingcpp
from PIL import Image
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.main import create_app
from app.shared.db import Database
from tests.integration.api import PUBLIC_BASE_URL, api_client, api_settings, register

pytestmark = pytest.mark.anyio

PASSWORD = "contraseña-segura"
TENANT_TABLES = (
    "establishment",
    "owner_account",
    "data_authorization",
    "owner_session",
    "email_token",
    "email_outbox",
)


@dataclass
class Ctx:
    a: httpx2.AsyncClient  # con la sesión del propietario A
    engine: AsyncEngine  # superusuario, para comprobar sin RLS
    ids: dict[str, UUID]  # establishment_id por propietario
    codes: dict[str, str]  # public_code por propietario

    def b_markers(self) -> list[str]:
        """Todo lo que identifica a B y no debe aparecer nunca en lo que ve A."""
        return [str(self.ids["b"]), self.codes["b"], "b@ejemplo.com", "Café Ñandú"]


def _assert_nothing_of_b(ctx: Ctx, response: httpx2.Response) -> None:
    body = response.text + str(response.headers)
    leaked = [marker for marker in ctx.b_markers() if marker.lower() in body.lower()]
    assert leaked == [], (response.request.method, str(response.request.url), leaked)


async def _snapshot(engine: AsyncEngine, establishment_id: UUID) -> dict[str, Any]:
    """Todo lo de un establecimiento, tabla por tabla, para ver si algo cambió."""
    rows: dict[str, Any] = {}
    async with engine.connect() as connection:
        for table in TENANT_TABLES:
            result = await connection.execute(
                text(
                    f"SELECT row_to_json(t)::text AS j FROM {table} t WHERE establishment_id = :e "
                    "ORDER BY j"
                ),
                {"e": establishment_id},
            )
            rows[table] = list(result.scalars())
    return rows


@pytest.fixture
async def ctx(engine: AsyncEngine, database_url: str) -> AsyncIterator[Ctx]:
    async with api_client(create_app(api_settings(database_url))) as client:
        await register(client, "a@ejemplo.com", PASSWORD, "Bar La Esquina")
        await register(client, "b@ejemplo.com", PASSWORD, "Café Ñandú")
        async with engine.begin() as connection:
            # Los dos verificados, para que el QR de A no quede bloqueado por R018.
            await connection.execute(text("UPDATE owner_account SET email_verified_at = now()"))
            rows = (
                await connection.execute(
                    text(
                        "SELECT a.email, e.id, e.public_code FROM owner_account a "
                        "JOIN establishment e ON e.id = a.establishment_id"
                    )
                )
            ).all()
        ids = {row.email[0]: row.id for row in rows}
        codes = {row.email[0]: row.public_code for row in rows}
        # B también entra (en otro navegador), para que tenga filas en owner_session.
        async with httpx2.AsyncClient(
            transport=client._transport,
            base_url="https://api",
            headers=dict(client.headers),
        ) as b_client:
            b_login = await b_client.post(
                "/api/auth/login", json={"email": "b@ejemplo.com", "password": PASSWORD}
            )
            assert b_login.status_code == 200
        login = await client.post(
            "/api/auth/login", json={"email": "a@ejemplo.com", "password": PASSWORD}
        )
        assert login.status_code == 200
        ctx = Ctx(a=client, engine=engine, ids=ids, codes=codes)
        # Sin filas de B en una tabla, un «0 filas» no probaría nada.
        b_rows = await _snapshot(engine, ids["b"])
        assert [table for table, rows in b_rows.items() if not rows] == []
        yield ctx


async def test_F001_R015_sesion_de_a_no_lee_ni_modifica_b(ctx: Ctx) -> None:
    b_before = await _snapshot(ctx.engine, ctx.ids["b"])
    b_id = str(ctx.ids["b"])

    me = await ctx.a.get("/api/owner/me")
    assert me.status_code == 200
    assert me.json()["establishment"]["name"] == "Bar La Esquina"
    _assert_nothing_of_b(ctx, me)

    # Intentos de apuntar a B desde el cuerpo, la consulta o la URL, con el código que
    # se espera: las rutas válidas atienden a A y las inventadas no existen.
    attempts = [
        (
            "PATCH",
            "/api/owner/establishment",
            {"name": "Tomado", "establishment_id": b_id, "id": b_id, "public_code": ctx.codes["b"]},
            200,
        ),
        ("GET", f"/api/owner/me?establishment_id={b_id}", None, 200),
        ("PATCH", f"/api/owner/establishment?establishment_id={b_id}", {"phone": "666"}, 200),
        ("GET", f"/api/owner/establishment/qr.png?establishment_id={b_id}", None, 200),
        ("POST", f"/api/owner/email-verification/resend?establishment_id={b_id}", None, 409),
        ("GET", f"/api/owner/{b_id}", None, 404),
        ("GET", f"/api/owner/establishment/{b_id}", None, 404),
    ]
    for method, url, body, expected in attempts:
        response = await ctx.a.request(method, url, json=body)
        assert response.status_code == expected, (method, url, response.text)
        _assert_nothing_of_b(ctx, response)

    # Lo único que cambió es A; B queda exactamente igual.
    assert await _snapshot(ctx.engine, ctx.ids["b"]) == b_before
    async with ctx.engine.connect() as connection:
        names = await connection.execute(text("SELECT name FROM establishment ORDER BY name"))
        assert list(names.scalars()) == ["Café Ñandú", "Tomado"]


async def test_F001_R015_qr_de_a_nunca_codifica_b(ctx: Ctx) -> None:
    b_id = str(ctx.ids["b"])
    for params in ({}, {"download": "1"}, {"establishment_id": b_id}):
        response = await ctx.a.get("/api/owner/establishment/qr.png", params=params)
        assert response.status_code == 200

        decoded = [r.text for r in zxingcpp.read_barcodes(Image.open(io.BytesIO(response.content)))]

        assert decoded == [f"{PUBLIC_BASE_URL}/l/{ctx.codes['a']}"]
        assert ctx.codes["b"] not in response.headers.get("content-disposition", "")


async def test_F001_R015_consulta_directa_con_rol_app_api_no_ve_b(ctx: Ctx) -> None:
    api = Database(ctx.engine, role="app_api")
    b_before = await _snapshot(ctx.engine, ctx.ids["b"])

    async with api.transaction(establishment_id=ctx.ids["a"]) as connection:
        for table in TENANT_TABLES:
            foreign = await connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE establishment_id = :b"),
                {"b": ctx.ids["b"]},
            )
            assert foreign.scalar_one() == 0, table
            total = await connection.execute(text(f"SELECT count(*) FROM {table}"))
            own = await connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE establishment_id = :a"),
                {"a": ctx.ids["a"]},
            )
            assert total.scalar_one() == own.scalar_one(), table

        for statement in (
            "UPDATE establishment SET name = 'Tomado' WHERE id = :b",
            "UPDATE owner_account SET email = 'x@ejemplo.com' WHERE establishment_id = :b",
            "UPDATE owner_session SET revoked_at = now() WHERE establishment_id = :b",
            "DELETE FROM email_token WHERE establishment_id = :b",
            "DELETE FROM email_outbox WHERE establishment_id = :b",
        ):
            result = await connection.execute(text(statement), {"b": ctx.ids["b"]})
            assert result.rowcount == 0, statement

    # Insertar a nombre de B, aun sabiendo su id, lo rechaza la política.
    with pytest.raises(DBAPIError, match="row-level security"):
        async with api.transaction(establishment_id=ctx.ids["a"]) as connection:
            await connection.execute(
                text(
                    "INSERT INTO email_outbox (establishment_id, to_address, "
                    "to_address_normalized, template) "
                    "VALUES (:b, 'b@ejemplo.com', 'b@ejemplo.com', 'verify_email')"
                ),
                {"b": ctx.ids["b"]},
            )

    assert await _snapshot(ctx.engine, ctx.ids["b"]) == b_before


async def test_F001_R015_aviso_de_registro_duplicado_solo_se_encola_en_el_establecimiento_del_titular(ctx: Ctx) -> None:  # noqa: E501  # fmt: skip
    a_before = await _snapshot(ctx.engine, ctx.ids["a"])

    # Desde la sesión de A, alguien intenta registrarse con el correo de B.
    await register(ctx.a, "B@Ejemplo.com", "otra-contraseña", "Otro bar")

    async with ctx.engine.connect() as connection:
        notices = (
            await connection.execute(
                text(
                    "SELECT establishment_id, to_address FROM email_outbox "
                    "WHERE template = 'registration_attempt'"
                )
            )
        ).all()
    assert [(n.establishment_id, n.to_address) for n in notices] == [
        (ctx.ids["b"], "b@ejemplo.com")
    ]
    # Nada nuevo ni cambiado en A, ni establecimientos de más.
    assert await _snapshot(ctx.engine, ctx.ids["a"]) == a_before
    async with ctx.engine.connect() as connection:
        total = await connection.execute(text("SELECT count(*) FROM establishment"))
        assert total.scalar_one() == 2


# Feature 002 (sesión de música): A intenta abrir, cerrar, poner en marcha, informar
# y consultar la sesión de B (R013, ADR-0009).
B_SONG = "Canción secreta de B"
MUSIC_TABLES = ("music_session", "queue_item")


async def _b_music_session(ctx: Ctx) -> dict[str, Any]:
    """B tiene una sesión abierta con una canción sonando, una pendiente y una saltada."""
    async with ctx.engine.begin() as connection:
        session_id = (
            await connection.execute(
                text(
                    "INSERT INTO music_session (establishment_id, player_epoch, player_seen_at, "
                    "version) VALUES (:b, 2, now(), 5) RETURNING id"
                ),
                {"b": ctx.ids["b"]},
            )
        ).scalar_one()
        items = {}
        for position, (title, state, reason) in enumerate(
            (
                ("Saltada de B", "skipped", "not_embeddable"),
                (B_SONG, "playing", None),
                ("Pendiente de B", "pending", None),
            ),
            start=1,
        ):
            items[state] = (
                await connection.execute(
                    text(
                        "INSERT INTO queue_item (establishment_id, session_id, position, "
                        "track_ref, title, state, failure_reason, finished_at) "
                        "VALUES (:b, :s, :p, 'fake:b', :title, CAST(:state AS queue_item_state), "
                        "CAST(:reason AS text), CASE WHEN CAST(:reason AS text) IS NULL THEN NULL "
                        "ELSE now() END) RETURNING id"
                    ),
                    {
                        "b": ctx.ids["b"],
                        "s": session_id,
                        "p": position,
                        "title": title,
                        "state": state,
                        "reason": reason,
                    },
                )
            ).scalar_one()
    # Sin filas de B, un «B no cambió» no probaría nada.
    seeded = await _b_music(ctx)
    assert (len(seeded["music_session"]), len(seeded["queue_item"])) == (1, 3)
    return {"session_id": session_id, "items": items}


async def _b_music(ctx: Ctx) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    async with ctx.engine.connect() as connection:
        for table in MUSIC_TABLES:
            result = await connection.execute(
                text(
                    f"SELECT row_to_json(t)::text AS j FROM {table} t WHERE establishment_id = :e "
                    "ORDER BY j"
                ),
                {"e": ctx.ids["b"]},
            )
            rows[table] = list(result.scalars())
    return rows


def _assert_nothing_of_b_music(ctx: Ctx, response: httpx2.Response, b: dict[str, Any]) -> None:
    _assert_nothing_of_b(ctx, response)
    body = response.text
    markers = [B_SONG, "Saltada de B", "Pendiente de B", str(b["session_id"])]
    markers += [str(item_id) for item_id in b["items"].values()]
    leaked = [marker for marker in markers if marker in body]
    assert leaked == [], (response.request.method, str(response.request.url), leaked)


async def test_F002_R013_sesion_de_a_no_abre_ni_cierra_la_de_b(ctx: Ctx) -> None:
    b = await _b_music_session(ctx)
    b_before = await _b_music(ctx)
    b_id = str(ctx.ids["b"])

    # Apuntar a B desde el cuerpo o la consulta: las rutas atienden siempre a A.
    opened = await ctx.a.post(
        f"/api/owner/music-session?establishment_id={b_id}", json={"establishment_id": b_id}
    )
    assert opened.status_code == 201
    _assert_nothing_of_b_music(ctx, opened, b)
    closed = await ctx.a.delete(f"/api/owner/music-session?establishment_id={b_id}")
    assert closed.status_code == 204
    # El DELETE cerró la de A, no la de B.
    assert (await ctx.a.get("/api/owner/music-session")).json()["status"] == "closed"
    # Y sin sesión propia, cerrar otra vez no toca la de B.
    again = await ctx.a.delete("/api/owner/music-session")
    assert again.status_code == 204

    assert await _b_music(ctx) == b_before
    async with ctx.engine.connect() as connection:
        own = await connection.execute(
            text("SELECT count(*) FROM music_session WHERE establishment_id = :a"),
            {"a": ctx.ids["a"]},
        )
        assert own.scalar_one() == 1


async def test_F002_R013_reproductor_de_a_no_reclama_ni_informa_en_b(ctx: Ctx) -> None:
    b = await _b_music_session(ctx)
    b_before = await _b_music(ctx)
    b_id = str(ctx.ids["b"])
    assert (await ctx.a.post("/api/owner/music-session")).status_code == 201

    # A pone en marcha su reproductor, también apuntando a B: recibe su sesión, vacía.
    claim = await ctx.a.post(f"/api/owner/music-session/player?establishment_id={b_id}")
    assert claim.status_code == 200
    assert (claim.json()["epoch"], claim.json()["current"]) == (1, None)
    _assert_nothing_of_b_music(ctx, claim, b)

    # Informar con las canciones de B, con la época de A o la de B: no existen para A.
    for item_id in b["items"].values():
        for epoch in (1, 2):
            for type in ("started", "ended", "failed"):
                response = await ctx.a.post(
                    "/api/owner/music-session/player/events",
                    json={"epoch": epoch, "item_id": str(item_id), "type": type},
                )
                # Con la época de A, la canción no es de su sesión; con la de B, la época
                # ni siquiera es la vigente de A.
                expected = (
                    (404, {"error": "not_found"})
                    if epoch == 1
                    else (409, {"error": "player_superseded"})
                )
                assert (response.status_code, response.json()) == expected, response.text
                _assert_nothing_of_b_music(ctx, response, b)

    # El latido con la época de B tampoco cuenta para B.
    beat = await ctx.a.post(
        f"/api/owner/music-session/player/heartbeat?establishment_id={b_id}", json={"epoch": 2}
    )
    assert (beat.status_code, beat.json()) == (409, {"error": "player_superseded"})
    _assert_nothing_of_b_music(ctx, beat, b)

    assert await _b_music(ctx) == b_before


async def test_F002_R013_get_music_session_de_a_no_muestra_lo_que_suena_en_b(ctx: Ctx) -> None:
    b = await _b_music_session(ctx)
    b_id = str(ctx.ids["b"])

    # Sin sesión propia, A no ve la de B: para A no hay ninguna abierta.
    closed = await ctx.a.get(f"/api/owner/music-session?establishment_id={b_id}")
    assert closed.json() == {"status": "closed", "session": None}
    _assert_nothing_of_b_music(ctx, closed, b)

    assert (await ctx.a.post("/api/owner/music-session")).status_code == 201
    own = await ctx.a.get(f"/api/owner/music-session?establishment_id={b_id}")
    session = own.json()["session"]
    assert (session["now_playing"], session["failures"], session["player_active"]) == (
        None,
        [],
        False,
    )
    _assert_nothing_of_b_music(ctx, own, b)
