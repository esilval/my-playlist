"""Reloj de sistema: el adaptador real del puerto Clock."""

from datetime import UTC, datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
