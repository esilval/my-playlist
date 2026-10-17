"""Caso de uso: editar los datos del establecimiento (R014, R019).

El establecimiento es siempre el de la sesión (D9); el QR no cambia (R009, R014).
"""

from dataclasses import dataclass

from app.accounts.domain.establishment import validate_establishment_changes
from app.accounts.domain.ports import AccountsUnitOfWork, Clock, OwnerProfile
from app.accounts.interface import OwnerContext


@dataclass(frozen=True)
class UpdateEstablishment:
    unit_of_work: AccountsUnitOfWork
    clock: Clock

    async def __call__(self, owner: OwnerContext, submitted: dict[str, str | None]) -> OwnerProfile:
        """Lanza RegistrationRejected si un campo no vale."""
        changes = validate_establishment_changes(submitted)
        async with self.unit_of_work(owner.establishment_id) as accounts:
            await accounts.update_establishment(owner.establishment_id, changes, self.clock.now())
            return await accounts.owner_profile(owner.account_id, owner.establishment_id)
