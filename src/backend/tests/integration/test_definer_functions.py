import hashlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.shared.db import Database, set_establishment

pytestmark = pytest.mark.anyio


@dataclass
class Ctx:
    engine: AsyncEngine  # superusuario, para preparar datos sin RLS
    db: Database  # como la API: rol app_api


@pytest.fixture
async def ctx(engine: AsyncEngine) -> AsyncIterator[Ctx]:
    yield Ctx(engine=engine, db=Database(engine, role="app_api"))


async def _seed(connection: AsyncConnection, *, code: str, email: str) -> dict[str, uuid.UUID]:
    """Crea establecimiento, cuenta, sesión y token como superusuario."""
    establishment_id = uuid.uuid4()
    await connection.execute(
        text(
            "INSERT INTO establishment (id, establishment_id, public_code, name, address, phone) "
            "VALUES (:id, :id, :code, 'Bar La Esquina', 'Calle 1', '3000000000')"
        ),
        {"id": establishment_id, "code": code},
    )
    account_id = (
        await connection.execute(
            text(
                "INSERT INTO owner_account (establishment_id, email, email_normalized, "
                "password_hash) VALUES (:id, :email, lower(:email), 'hash-secreto') RETURNING id"
            ),
            {"id": establishment_id, "email": email},
        )
    ).scalar_one()
    for table, extra_cols, extra_vals in (
        ("owner_session", "", ""),
        ("email_token", ", purpose", ", 'verify'"),
    ):
        await connection.execute(
            text(
                f"INSERT INTO {table} (establishment_id, account_id, token_hash{extra_cols}) "
                f"VALUES (:id, :account, :hash{extra_vals})"
            ),
            {"id": establishment_id, "account": account_id, "hash": _hash(f"{email}-{table}")},
        )
    return {"establishment": establishment_id, "account": account_id}


def _hash(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


async def test_F001_R012_public_establishment_devuelve_solo_nombre(ctx: Ctx) -> None:
    async with ctx.engine.begin() as connection:
        await _seed(connection, code="AAAAAAAAAA", email="a@ejemplo.com")

    async with ctx.db.transaction() as connection:
        result = await connection.execute(
            text("SELECT * FROM public_establishment(:code)"), {"code": "AAAAAAAAAA"}
        )
        assert list(result.keys()) == ["name"]
        assert result.all() == [("Bar La Esquina",)]


async def test_F001_R013_public_establishment_desconocido_devuelve_nada(ctx: Ctx) -> None:
    async with ctx.engine.begin() as connection:
        await _seed(connection, code="AAAAAAAAAA", email="a@ejemplo.com")

    async with ctx.db.transaction() as connection:
        for code in ("ZZZZZZZZZZ", "", "AAAAAAAAA", "AAAAAAAAAAB", "AAAAAAAAAA' OR '1'='1"):
            rows = await connection.execute(
                text("SELECT * FROM public_establishment(:code)"), {"code": code}
            )
            assert rows.all() == [], code


async def test_F003_R001_public_establishment_id_devuelve_solo_el_identificador(ctx: Ctx) -> None:
    async with ctx.engine.begin() as connection:
        ids = await _seed(connection, code="AAAAAAAAAA", email="a@ejemplo.com")
        await _seed(connection, code="BBBBBBBBBB", email="b@ejemplo.com")

    async with ctx.db.transaction() as connection:
        result = await connection.execute(
            text("SELECT * FROM public_establishment_id(:code)"), {"code": "AAAAAAAAAA"}
        )
        # Ni el nombre, ni la dirección, ni nada de la cuenta: solo el identificador.
        assert list(result.keys()) == ["establishment_id"]
        assert result.all() == [(ids["establishment"],)]
        # La función de la feature 001 sigue devolviendo solo el nombre.
        names = await connection.execute(
            text("SELECT * FROM public_establishment(:code)"), {"code": "AAAAAAAAAA"}
        )
        assert list(names.keys()) == ["name"]


async def test_F003_R011_public_establishment_id_de_un_codigo_desconocido_o_mal_formado_no_devuelve_nada(  # noqa: E501
    ctx: Ctx,
) -> None:
    async with ctx.engine.begin() as connection:
        await _seed(connection, code="AAAAAAAAAA", email="a@ejemplo.com")

    async with ctx.db.transaction() as connection:
        for code in ("ZZZZZZZZZZ", "", "AAAAAAAAA", "AAAAAAAAAAB", "AAAAAAAAAA' OR '1'='1"):
            rows = await connection.execute(
                text("SELECT * FROM public_establishment_id(:code)"), {"code": code}
            )
            assert rows.all() == [], code


async def test_F001_R015_auth_account_by_email_no_expone_otros_campos(ctx: Ctx) -> None:
    async with ctx.engine.begin() as connection:
        ids = await _seed(connection, code="AAAAAAAAAA", email="a@ejemplo.com")
        await _seed(connection, code="BBBBBBBBBB", email="b@ejemplo.com")

    async with ctx.db.transaction() as connection:
        result = await connection.execute(
            text("SELECT * FROM auth_account_by_email(:email)"), {"email": "  A@Ejemplo.com "}
        )
        assert list(result.keys()) == [
            "account_id",
            "establishment_id",
            "password_hash",
            "email_verified",
        ]
        assert result.all() == [(ids["account"], ids["establishment"], "hash-secreto", False)]


async def test_F001_R015_auth_session_y_auth_email_token_resuelven_solo_su_fila(ctx: Ctx) -> None:
    async with ctx.engine.begin() as connection:
        ids = await _seed(connection, code="AAAAAAAAAA", email="a@ejemplo.com")
        await _seed(connection, code="BBBBBBBBBB", email="b@ejemplo.com")

    async with ctx.db.transaction() as connection:
        session = await connection.execute(
            text("SELECT * FROM auth_session(:hash)"),
            {"hash": _hash("a@ejemplo.com-owner_session")},
        )
        assert list(session.keys()) == [
            "session_id",
            "account_id",
            "establishment_id",
            "last_seen_at",
            "revoked_at",
        ]
        assert [(r.account_id, r.establishment_id) for r in session] == [
            (ids["account"], ids["establishment"])
        ]

        token = await connection.execute(
            text("SELECT * FROM auth_email_token(:hash, 'verify')"),
            {"hash": _hash("a@ejemplo.com-email_token")},
        )
        assert list(token.keys()) == [
            "token_id",
            "account_id",
            "establishment_id",
            "expires_at",
            "used_at",
            "superseded_at",
            "email_verified",
        ]
        assert [(r.account_id, r.email_verified) for r in token] == [(ids["account"], False)]

        wrong_purpose = await connection.execute(
            text("SELECT * FROM auth_email_token(:hash, 'reset')"),
            {"hash": _hash("a@ejemplo.com-email_token")},
        )
        assert wrong_purpose.all() == []


DEFINER_CALLS = {
    "auth_account_by_email": "SELECT * FROM auth_account_by_email('a@ejemplo.com')",
    "auth_session": "SELECT * FROM auth_session('\\x00'::bytea)",
    "auth_email_token": "SELECT * FROM auth_email_token('\\x00'::bytea, 'verify')",
    "public_establishment": "SELECT * FROM public_establishment('AAAAAAAAAA')",
    "public_establishment_id": "SELECT * FROM public_establishment_id('AAAAAAAAAA')",
}


@pytest.mark.parametrize("function", sorted(DEFINER_CALLS))
async def test_F001_R015_solo_app_api_ejecuta_las_funciones(ctx: Ctx, function: str) -> None:
    worker = Database(ctx.engine, role="app_worker")
    with pytest.raises(DBAPIError) as denied:
        async with worker.transaction() as connection:
            await connection.execute(text(DEFINER_CALLS[function]))
    assert f"permission denied for function {function}" in str(denied.value)

    async with ctx.db.transaction() as connection:
        await connection.execute(text(DEFINER_CALLS[function]))


async def test_F001_R015_transaccion_aplica_rls_aunque_conecte_un_superusuario(ctx: Ctx) -> None:
    async with ctx.engine.begin() as connection:
        a = await _seed(connection, code="AAAAAAAAAA", email="a@ejemplo.com")
        await _seed(connection, code="BBBBBBBBBB", email="b@ejemplo.com")

    async with ctx.db.transaction(establishment_id=a["establishment"]) as connection:
        role = await connection.execute(text("SELECT current_user"))
        assert role.scalar_one() == "app_api"
        names = await connection.execute(text("SELECT public_code FROM establishment"))
        assert names.scalars().all() == ["AAAAAAAAAA"]


async def test_F001_R015_contexto_fijado_a_mitad_de_transaccion(ctx: Ctx) -> None:
    async with ctx.engine.begin() as connection:
        a = await _seed(connection, code="AAAAAAAAAA", email="a@ejemplo.com")

    async with ctx.db.transaction() as connection:
        found = await connection.execute(
            text("SELECT establishment_id FROM auth_account_by_email('a@ejemplo.com')")
        )
        await set_establishment(connection, found.scalar_one())
        accounts = await connection.execute(text("SELECT id FROM owner_account"))
        assert accounts.scalars().all() == [a["account"]]


async def test_F001_R015_transaccion_sin_contexto_no_lee_tablas(ctx: Ctx) -> None:
    async with ctx.engine.begin() as connection:
        await _seed(connection, code="AAAAAAAAAA", email="a@ejemplo.com")

    with pytest.raises(DBAPIError) as failed:
        async with ctx.db.transaction() as connection:
            await connection.execute(text("SELECT count(*) FROM establishment"))
    # Según la conexión del pool, el parámetro no existe (nunca se fijó) o quedó vacío
    # tras una transacción anterior; en ambos casos la consulta falla.
    message = str(failed.value)
    assert (
        'unrecognized configuration parameter "app.establishment_id"' in message
        or 'invalid input syntax for type uuid: ""' in message
    )
