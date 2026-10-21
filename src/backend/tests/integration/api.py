"""Cliente HTTP de pruebas contra la API real, con la base de pruebas."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from fastapi import APIRouter, FastAPI

from app.accounts.api.deps import CurrentOwner
from app.main import create_app
from app.shared.config import Settings

PUBLIC_BASE_URL = "https://myplaylist.test"


def api_settings(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        email_backend="memory",
        public_base_url=PUBLIC_BASE_URL,
        # Argon2 barato en pruebas; el coste real se fija con la prueba de carga (T023).
        argon2_time_cost=1,
        argon2_memory_cost_kib=8192,
        argon2_parallelism=1,
    )


@asynccontextmanager
async def api_client(app: FastAPI) -> AsyncIterator[httpx2.AsyncClient]:
    """Como la SPA: mismo origen, cabecera propia (D9) y https para la cookie Secure."""
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="https://api",
        headers={"X-MyPlaylist-Client": "web", "Origin": PUBLIC_BASE_URL},
    ) as client:
        yield client
    await app.state.event_publisher.aclose()
    await app.state.db.dispose()


# Ruta protegida solo de pruebas: ejercita current_owner, la dependencia que protege
# todo /api/owner/* (la API del panel llega con T014).
probe_router = APIRouter()


@probe_router.get("/api/owner/_probe")
async def probe(owner: CurrentOwner) -> dict[str, str | bool]:
    return {
        "account_id": str(owner.account_id),
        "establishment_id": str(owner.establishment_id),
        "email_verified": owner.email_verified,
    }


def build_app_with_probe(database_url: str) -> FastAPI:
    app = create_app(api_settings(database_url))
    app.include_router(probe_router)
    return app


async def register(client: httpx2.AsyncClient, email: str, password: str, name: str) -> None:
    from app.accounts.domain.data_policy import DRAFT_VERSION

    response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": password,
            "establishment_name": name,
            "data_authorization": True,
            "policy_version": DRAFT_VERSION,
        },
    )
    assert response.status_code == 202, response.text
