"""Bloqueo por intentos fallidos de inicio de sesión (R007, plan D5).

Con 5 fallos sobre un correo dentro de 15 minutos, el correo queda bloqueado 15
minutos completos contados desde el quinto fallo.

Solo cuentan como fallos las contraseñas incorrectas. Un intento rechazado por el
propio bloqueo no se verifica y no debe registrarse como fallo: si contara, cada
intento alargaría el bloqueo y el correo no se desbloquearía nunca.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta

MAX_FAILURES = 5
FAILURE_WINDOW = timedelta(minutes=15)
LOCK_DURATION = timedelta(minutes=15)
# Fallos que hay que consultar para decidir: los que aún pueden mantener un bloqueo.
LOOKBACK = FAILURE_WINDOW + LOCK_DURATION


def locked_until(failures: Iterable[datetime]) -> datetime | None:
    """Fin del bloqueo más reciente que provocan estos fallos, si hay alguno."""
    ordered = sorted(failures)
    ends = [
        ordered[i] + LOCK_DURATION
        for i in range(MAX_FAILURES - 1, len(ordered))
        if ordered[i] - ordered[i - MAX_FAILURES + 1] <= FAILURE_WINDOW
    ]
    return max(ends, default=None)


def is_locked(failures: Iterable[datetime], now: datetime) -> bool:
    until = locked_until(failures)
    return until is not None and now < until
