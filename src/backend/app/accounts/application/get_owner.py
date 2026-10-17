"""Caso de uso: los datos del panel del propietario (R014, R019, plan Contratos /me)."""

from dataclasses import dataclass

from app.accounts.domain.ports import AccountsUnitOfWork, OwnerProfile
from app.accounts.interface import OwnerContext


@dataclass(frozen=True)
class GetOwnerProfile:
    unit_of_work: AccountsUnitOfWork

    async def __call__(self, owner: OwnerContext) -> OwnerProfile:
        async with self.unit_of_work(owner.establishment_id) as accounts:
            return await accounts.owner_profile(owner.account_id, owner.establishment_id)
