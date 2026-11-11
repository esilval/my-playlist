"""Métricas en el formato EMF de CloudWatch (feature 004, plan D11, ADR-0018).

Cada métrica es una línea JSON en la salida estándar. CloudWatch Logs la guarda como
registro y, por su bloque `_aws`, la convierte en métrica, sin agente ni llamadas de red:
https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Specification.html
"""

import json
import sys
import time
from collections.abc import Callable
from typing import Any

from app.shared.metrics import ALLOWED_DIMENSIONS, Unit, check_dimensions


def namespace_for(env: str) -> str:
    """El espacio de nombres de las métricas de un entorno: `MyPlaylist/production`."""
    return f"MyPlaylist/{env}"


def emf_fields(
    namespace: str,
    name: str,
    value: float,
    unit: Unit,
    dimensions: dict[str, str],
    timestamp_ms: int | None = None,
) -> dict[str, Any]:
    """Los campos EMF de una métrica, para escribirlos solos o dentro de otra línea de
    registro (el registro por petición de T003)."""
    check_dimensions(dimensions)
    # El valor va en la raíz con el nombre de la métrica: no puede pisar una dimensión ni el
    # bloque de EMF.
    if name in ALLOWED_DIMENSIONS or name == "_aws":
        raise ValueError(f"nombre de métrica no admitido: {name}")
    return {
        "_aws": {
            "Timestamp": timestamp_ms if timestamp_ms is not None else int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": namespace,
                    "Dimensions": [sorted(dimensions)],
                    "Metrics": [{"Name": name, "Unit": unit}],
                }
            ],
        },
        **dimensions,
        name: value,
    }


def _write_line(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


class EmfMetrics:
    """Implementación del puerto `Metrics` que escribe una línea EMF por métrica."""

    def __init__(self, namespace: str, write: Callable[[str], None] = _write_line) -> None:
        self.namespace = namespace
        self._write = write

    def count(self, name: str, value: float = 1, **dimensions: str) -> None:
        self._emit(name, value, "Count", dimensions)

    def timing(self, name: str, ms: float, **dimensions: str) -> None:
        self._emit(name, ms, "Milliseconds", dimensions)

    def _emit(self, name: str, value: float, unit: Unit, dimensions: dict[str, str]) -> None:
        line = {"event": "metric", **emf_fields(self.namespace, name, value, unit, dimensions)}
        self._write(json.dumps(line, ensure_ascii=False))
