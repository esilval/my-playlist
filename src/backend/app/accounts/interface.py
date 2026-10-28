"""Interfaz pública de C1 (cuentas y establecimientos) para los demás módulos.

Plan, Contratos:
- `resolve_owner(session_token) -> OwnerContext | None` (instancia en
  `app.state.resolve_owner`);
- `establishment_by_public_code(code) -> PublicEstablishment | None` (instancia en
  `app.state.establishment_by_public_code`);
- `establishment_id_by_public_code(code) -> UUID | None` (feature 003, plan D5; instancia
  en `app.state.establishment_id_by_public_code`).

Los otros módulos (B02, B03…) los usan sin tocar las tablas de C1.
"""

from app.accounts.application.get_public_establishment import (
    GetPublicEstablishment as EstablishmentByPublicCode,
)
from app.accounts.application.get_public_establishment import (
    GetPublicEstablishmentId as EstablishmentIdByPublicCode,
)
from app.accounts.application.get_public_establishment import PublicEstablishment
from app.accounts.application.resolve_session import OwnerContext
from app.accounts.application.resolve_session import ResolveSession as ResolveOwner

__all__ = [
    "EstablishmentByPublicCode",
    "EstablishmentIdByPublicCode",
    "OwnerContext",
    "PublicEstablishment",
    "ResolveOwner",
]
