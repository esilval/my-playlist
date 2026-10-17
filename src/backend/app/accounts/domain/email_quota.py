"""Límite de correos por destinatario (R027, plan D7).

Como mucho 3 correos de un mismo tipo (recuperación, reenvío de verificación o aviso
de intento de registro) a un mismo correo en 60 minutos. La verificación inicial del
registro no cuenta: solo ocurre una vez por cuenta.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta

MAX_PER_WINDOW = 3
WINDOW = timedelta(minutes=60)


def quota_allows(previous: Iterable[datetime], now: datetime) -> bool:
    """¿Se puede enviar otro, dados los envíos anteriores de ese tipo a ese correo?"""
    recent = [sent_at for sent_at in previous if now - sent_at < WINDOW]
    return len(recent) < MAX_PER_WINDOW
