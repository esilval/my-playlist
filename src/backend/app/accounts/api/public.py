"""Rutas públicas, sin sesión (plan Contratos: /api/public/*)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.accounts.application.get_data_policy import get_current_data_policy
from app.accounts.domain.ports import PolicyStore
from app.accounts.interface import EstablishmentByPublicCode
from app.shared.config import Settings

router = APIRouter(prefix="/public")


class DataPolicyOut(BaseModel):
    version: str
    content: str


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _policy_store(request: Request) -> PolicyStore:
    store: PolicyStore = request.app.state.policy_store
    return store


@router.get("/data-policy")
async def data_policy(
    settings: Annotated[Settings, Depends(_settings)],
    store: Annotated[PolicyStore, Depends(_policy_store)],
) -> DataPolicyOut:
    policy = get_current_data_policy(store, settings.data_policy_version)
    return DataPolicyOut(version=policy.version, content=policy.content)


class PublicEstablishmentOut(BaseModel):
    name: str


def _establishment_by_public_code(request: Request) -> EstablishmentByPublicCode:
    lookup: EstablishmentByPublicCode = request.app.state.establishment_by_public_code
    return lookup


@router.get(
    # `:path` para que un código con «/» también reciba el mismo 404 (R013).
    "/establishments/{code:path}",
    response_model=PublicEstablishmentOut,
    responses={404: {"description": "not_found"}},
)
async def public_establishment(
    code: str, lookup: Annotated[EstablishmentByPublicCode, Depends(_establishment_by_public_code)]
) -> PublicEstablishmentOut | JSONResponse:
    establishment = await lookup(code)
    if establishment is None:
        # El mismo 404 para un código inexistente o mal formado: no se revela nada (R013).
        return JSONResponse(status_code=404, content={"error": "not_found"})
    return PublicEstablishmentOut(name=establishment.name)
