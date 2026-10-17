"""Caso de uso: identificar al propietario por su cookie de sesión (R008, R015, R020).

Se publica como `resolve_owner(session_token) -> OwnerContext | None`, la interfaz
de C1 para los demás módulos (plan Contratos); ver app/accounts/interface.py.
"""

from dataclasses import dataclass
from uuid import UUID

from app.accounts.domain.ports import AccountsUnitOfWork, Clock
from app.accounts.domain.session_policy import hash_session_token, is_session_active


@dataclass(frozen=True)
class OwnerContext:
    account_id: UUID
    establishment_id: UUID
    email_verified: bool


@dataclass(frozen=True)
class ResolveSession:
    unit_of_work: AccountsUnitOfWork
    clock: Clock

    async def __call__(self, token: str | None) -> OwnerContext | None:
        if not token:
            return None
        now = self.clock.now()
        async with self.unit_of_work() as accounts:
            session = await accounts.session_by_token_hash(hash_session_token(token))
            if session is None or not is_session_active(
                last_seen_at=session.last_seen_at, revoked_at=session.revoked_at, now=now
            ):
                return None
            await accounts.use_establishment(session.establishment_id)
            # Cada petición renueva el plazo de inactividad de 12 h (R020, D2).
            await accounts.touch_session(session.session_id, now)
            verified = await accounts.email_verified(session.account_id)
        return OwnerContext(
            account_id=session.account_id,
            establishment_id=session.establishment_id,
            email_verified=verified,
        )
