"""Puerto de métricas de la aplicación (feature 004, plan D11, ADR-0018).

Los casos de uso cuentan y miden a través de este puerto, sin saber cómo se emiten: la
implementación EMF (`app.shared.infrastructure.emf`) escribe líneas que CloudWatch convierte
en métricas, y las pruebas usan la de memoria.

Solo se admiten las dimensiones `Route` y `Service`: una métrica por establecimiento o por
dispositivo crearía una serie por cada uno, con su coste (ADR-0018).
"""

from dataclasses import dataclass, field
from typing import Literal, Protocol

ALLOWED_DIMENSIONS = frozenset({"Route", "Service"})

Unit = Literal["Count", "Milliseconds"]


def check_dimensions(dimensions: dict[str, str]) -> None:
    """Rechaza cualquier dimensión fuera de `Route` y `Service`."""
    unknown = set(dimensions) - ALLOWED_DIMENSIONS
    if unknown:
        raise ValueError(
            f"dimensiones no admitidas en una métrica: {', '.join(sorted(unknown))}; "
            f"solo {', '.join(sorted(ALLOWED_DIMENSIONS))} (ADR-0018)"
        )


class Metrics(Protocol):
    def count(self, name: str, value: float = 1, **dimensions: str) -> None: ...

    def timing(self, name: str, ms: float, **dimensions: str) -> None: ...


@dataclass(frozen=True)
class Recorded:
    name: str
    value: float
    unit: Unit
    dimensions: dict[str, str]


@dataclass
class InMemoryMetrics:
    """Métricas en memoria para las pruebas: guarda lo emitido."""

    recorded: list[Recorded] = field(default_factory=list)

    def count(self, name: str, value: float = 1, **dimensions: str) -> None:
        check_dimensions(dimensions)
        self.recorded.append(Recorded(name, value, "Count", dimensions))

    def timing(self, name: str, ms: float, **dimensions: str) -> None:
        check_dimensions(dimensions)
        self.recorded.append(Recorded(name, ms, "Milliseconds", dimensions))

    def values(self, name: str) -> list[float]:
        return [item.value for item in self.recorded if item.name == name]
