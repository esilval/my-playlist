"""Caso de uso: la política de tratamiento vigente (R022)."""

from app.accounts.domain.data_policy import DataPolicy
from app.accounts.domain.ports import PolicyStore


def get_current_data_policy(store: PolicyStore, current_version: str) -> DataPolicy:
    return store.get(current_version)
