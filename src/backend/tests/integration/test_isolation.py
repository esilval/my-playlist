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
    return await _music_rows(ctx, "b")


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

    # Avanzar, con la época de A o la de B, solo mira la sesión de A, que está vacía.
    for epoch, status in ((1, 200), (2, 409)):
        advanced = await ctx.a.post(
            f"/api/owner/music-session/player/advance?establishment_id={b_id}",
            json={"epoch": epoch, "establishment_id": b_id},
        )
        assert advanced.status_code == status, advanced.text
        if status == 200:
            assert (advanced.json()["current"], advanced.json()["next"]) == (None, None)
        _assert_nothing_of_b_music(ctx, advanced, b)

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


# Feature 003: el cliente que pide desde el QR (R011, plan D3, D5). El establecimiento
# sale del código de la URL y la cookie del dispositivo tiene que ser de ese mismo.


def _public(ctx: Ctx, owner: str, route: str) -> str:
    return f"/api/public/establishments/{ctx.codes[owner]}/{route}"


def _phone(ctx: Ctx) -> httpx2.AsyncClient:
    """Un móvil nuevo, sin la sesión del propietario. Se cierra con `aclose`."""
    return httpx2.AsyncClient(
        transport=ctx.a._transport,
        base_url="https://api",
        headers={"X-MyPlaylist-Client": "web", "Origin": PUBLIC_BASE_URL},
    )


async def _arrive(ctx: Ctx, phone: httpx2.AsyncClient, owner: str) -> str:
    """Abre la página del QR de `owner` y devuelve la cookie de dispositivo que recibió."""
    response = await phone.get(_public(ctx, owner, "music"))
    assert response.status_code == 200
    token = phone.cookies.get("mp_device", path=f"/api/public/establishments/{ctx.codes[owner]}/")
    assert token
    return token


def _carry_cookie(ctx: Ctx, phone: httpx2.AsyncClient, token: str, owner: str) -> None:
    """Fuerza la cookie `token` en las rutas de `owner`: el navegador no la mandaría (Path),
    pero alguien puede copiarla a mano."""
    phone.cookies.clear()
    phone.cookies.set("mp_device", token, path=f"/api/public/establishments/{ctx.codes[owner]}/")


async def _music_rows(ctx: Ctx, owner: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    async with ctx.engine.connect() as connection:
        for table in MUSIC_TABLES:
            result = await connection.execute(
                text(
                    f"SELECT row_to_json(t)::text AS j FROM {table} t WHERE establishment_id = :e "
                    "ORDER BY j"
                ),
                {"e": ctx.ids[owner]},
            )
            rows[table] = list(result.scalars())
    return rows


def _assert_absent(response: httpx2.Response, markers: list[str]) -> None:
    body = response.text + str(response.headers)
    leaked = [marker for marker in markers if marker in body]
    assert leaked == [], (response.request.method, str(response.request.url), leaked)


async def test_F003_R011_con_la_cookie_de_a_en_b_es_un_dispositivo_nuevo_con_cupo_completo(
    ctx: Ctx,
) -> None:
    await _b_music_session(ctx)
    assert (await ctx.a.post("/api/owner/music-session")).status_code == 201
    async with _phone(ctx) as phone:
        token_a = await _arrive(ctx, phone, "a")
        for ref in ("fake:uno-1", "fake:uno-2"):
            assert (
                await phone.post(_public(ctx, "a", "requests"), json={"ref": ref})
            ).status_code == 201
        a_items = [str(row) for row in await _a_item_ids(ctx)]
        a_device = await _a_device(ctx)

        _carry_cookie(ctx, phone, token_a, "b")
        in_b = await phone.get(_public(ctx, "b", "music"))

        # La cookie de A viajó de verdad a B: sin ella, la prueba no probaría nada.
        assert f"mp_device={token_a}" in in_b.request.headers["cookie"]
        assert in_b.status_code == 200
        state = in_b.json()
        assert (state["mine"], state["quota"]) == ([], {"limit": 5, "free": 5})
        # B no reconoce la cookie de A: le emite una suya, de otro dispositivo.
        issued = in_b.headers["set-cookie"]
        assert issued.startswith("mp_device=")
        assert f"Path=/api/public/establishments/{ctx.codes['b']}/" in issued
        token_b = issued.split(";")[0].removeprefix("mp_device=")
        assert token_b != token_a
        _carry_cookie(ctx, phone, token_b, "b")
        a_markers = ["Canción 1 de uno", "Canción 2 de uno", *a_items, a_device, ctx.codes["a"]]
        _assert_absent(in_b, a_markers)

        # Con la cookie de B pide en B: entra en la cola de B como de otro dispositivo.
        accepted = await phone.post(_public(ctx, "b", "requests"), json={"ref": "fake:dos-1"})
        assert accepted.status_code == 201
        assert [track["title"] for track in accepted.json()["mine"]] == ["Canción 1 de dos"]
    async with ctx.engine.connect() as connection:
        devices = (
            await connection.execute(
                text(
                    "SELECT establishment_id, requested_by FROM queue_item "
                    "WHERE requested_by IS NOT NULL"
                )
            )
        ).all()
    by_establishment = {(row.establishment_id, row.requested_by) for row in devices}
    assert len({device for _, device in by_establishment}) == 2
    assert {establishment for establishment, _ in by_establishment} == {ctx.ids["a"], ctx.ids["b"]}


async def _a_device(ctx: Ctx) -> str:
    """El dispositivo que pidió en A (solo hay uno)."""
    async with ctx.engine.connect() as connection:
        result = await connection.execute(
            text("SELECT DISTINCT requested_by FROM queue_item WHERE establishment_id = :a"),
            {"a": ctx.ids["a"]},
        )
        return str(result.scalar_one())


async def _a_item_ids(ctx: Ctx) -> list[UUID]:
    async with ctx.engine.connect() as connection:
        result = await connection.execute(
            text("SELECT id FROM queue_item WHERE establishment_id = :a"), {"a": ctx.ids["a"]}
        )
        return list(result.scalars())


async def test_F003_R011_un_pedido_en_b_con_la_cookie_de_a_da_401_y_no_cambia_ninguna_cola(
    ctx: Ctx,
) -> None:
    b = await _b_music_session(ctx)
    assert (await ctx.a.post("/api/owner/music-session")).status_code == 201
    async with _phone(ctx) as phone:
        token_a = await _arrive(ctx, phone, "a")
        assert (
            await phone.post(_public(ctx, "a", "requests"), json={"ref": "fake:uno-1"})
        ).status_code == 201
        a_before = await _music_rows(ctx, "a")
        b_before = await _music_rows(ctx, "b")

        _carry_cookie(ctx, phone, token_a, "b")
        # Ni pedir, ni buscar, ni el ticket de tiempo real de B (D6): la cookie no vale.
        for method, route, body in (
            ("POST", "requests", {"ref": "fake:uno-2"}),
            ("POST", "requests", {"ref": "fake:b"}),
            ("GET", "search?q=uno", None),
            ("POST", "realtime-ticket", None),
        ):
            response = await phone.request(method, _public(ctx, "b", route), json=body)
            assert f"mp_device={token_a}" in response.request.headers["cookie"]
            assert (response.status_code, response.json()) == (401, {"error": "device_required"})
            _assert_absent(response, [B_SONG, "Pendiente de B", str(b["session_id"])])
            assert "set-cookie" not in response.headers

        # Tampoco con el código de A en la URL y el cuerpo apuntando a B: la ruta es la de A.
        _carry_cookie(ctx, phone, token_a, "a")
        own = await phone.post(
            _public(ctx, "a", f"requests?establishment_id={ctx.ids['b']}"),
            json={"ref": "fake:uno-1", "establishment_id": str(ctx.ids["b"])},
        )
        assert (own.status_code, own.json()) == (409, {"error": "already_queued"})

    assert await _music_rows(ctx, "a") == a_before
    assert await _music_rows(ctx, "b") == b_before


async def test_F003_R011_nadie_ve_los_pedidos_de_otro_dispositivo_ni_de_otro_establecimiento(
    ctx: Ctx,
) -> None:
    b = await _b_music_session(ctx)
    assert (await ctx.a.post("/api/owner/music-session")).status_code == 201
    phones = {"a1": _phone(ctx), "a2": _phone(ctx), "b1": _phone(ctx)}
    owner_of = {"a1": "a", "a2": "a", "b1": "b"}
    refs = {"a1": ["fake:uno-1", "fake:uno-2"], "a2": ["fake:dos-1"], "b1": ["fake:tres-1"]}
    titles = {
        "a1": ["Canción 1 de uno", "Canción 2 de uno"],
        "a2": ["Canción 1 de dos"],
        "b1": ["Canción 1 de tres"],
    }
    try:
        for name, phone in phones.items():
            await _arrive(ctx, phone, owner_of[name])
            for ref in refs[name]:
                response = await phone.post(
                    _public(ctx, owner_of[name], "requests"), json={"ref": ref}
                )
                assert response.status_code == 201

        async with ctx.engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT id, title, requested_by FROM queue_item "
                        "WHERE requested_by IS NOT NULL"
                    )
                )
            ).all()
        by_title = {row.title: row for row in rows}
        # De cada dispositivo: sus títulos, sus canciones y su identificador.
        markers = {
            name: [
                *titles[name],
                *(str(by_title[title].id) for title in titles[name]),
                str(by_title[titles[name][0]].requested_by),
            ]
            for name in phones
        }
        # Lo de B que no viene de un cliente, que en A no debe verse.
        b_own = [B_SONG, "Pendiente de B", str(b["session_id"]), *map(str, b["items"].values())]

        for name, phone in phones.items():
            owner = owner_of[name]
            others = [marker for other in phones if other != name for marker in markers[other]]
            if owner == "a":
                others += b_own
            # Lo único propio del dispositivo que podría salir es su identificador: tampoco.
            others.append(markers[name][-1])
            responses = [
                await phone.get(_public(ctx, owner, "music")),
                await phone.get(_public(ctx, owner, "search?q=jazz")),
                await phone.post(_public(ctx, owner, "realtime-ticket")),
                # Un pedido rechazado devuelve solo el error.
                await phone.post(_public(ctx, owner, "requests"), json={"ref": refs[name][0]}),
            ]
            assert [response.status_code for response in responses] == [200, 200, 200, 409]
            for response in responses:
                _assert_absent(response, others)
            mine = responses[0].json()["mine"]
            assert [track["title"] for track in mine] == titles[name]
    finally:
        for phone in phones.values():
            await phone.aclose()
