"""Política de tratamiento de datos personales versionada (R022, plan D12)."""

from dataclasses import dataclass

# Marcador hasta que el negocio aporte el texto definitivo (supuesto de la spec).
DRAFT_VERSION = "0000-borrador"


@dataclass(frozen=True)
class DataPolicy:
    version: str
    content: str
