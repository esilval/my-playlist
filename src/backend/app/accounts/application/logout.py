"""Caso de uso: cierre de sesión (R008, plan D2)."""

from dataclasses import dataclass

from app.accounts.domain.ports import AccountsUnitOfWork, Clock
from app.accounts.domain.session_policy import hash_session_token


@dataclass(frozen=True)
class LogoutOwner:
    unit_of_work: AccountsUnitOfWork
    clock: Clock

    async def __call__(self, token: str | None) -> None:
        """Revoca la sesión en el servidor; sin sesión, no hace nada."""
        if not token:
            return
        async with self.unit_of_work() as accounts:
            session = await accounts.session_by_token_hash(hash_session_token(token))
            if session is None:
                return
            await accounts.use_establishment(session.establishment_id)
            await accounts.revoke_session(session.session_id, self.clock.now())
