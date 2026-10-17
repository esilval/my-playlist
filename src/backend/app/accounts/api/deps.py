"""Dependencias de las rutas del propietario (plan D9, R015)."""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status

from app.accounts.interface import OwnerContext, ResolveOwner

SESSION_COOKIE = "mp_session"


def _resolve_owner(request: Request) -> ResolveOwner:
    resolve_owner: ResolveOwner = request.app.state.resolve_owner
    return resolve_owner


async def current_owner(
    resolve_owner: Annotated[ResolveOwner, Depends(_resolve_owner)],
    mp_session: Annotated[str | None, Cookie()] = None,
) -> OwnerContext:
    """El establecimiento sale siempre de la sesión, nunca de la URL ni del cuerpo (D9)."""
    owner = await resolve_owner(mp_session)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthenticated")
    return owner


CurrentOwner = Annotated[OwnerContext, Depends(current_owner)]
