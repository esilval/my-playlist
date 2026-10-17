"""Trabajador de la bandeja de salida: `python -m app.worker` (plan D7).

Corre en su propia tarea con el rol app_worker. Envía los correos pendientes y,
cada hora, purga los intentos de inicio de sesión antiguos (plan D5).
"""

import argparse
import asyncio
import logging
import os
from datetime import timedelta
from pathlib import Path

from sqlalchemy import text

from app.shared.config import get_settings
from app.shared.db import Database
from app.shared.email.factory import email_sender_from_settings
from app.shared.outbox import OutboxDispatcher

logger = logging.getLogger("app.worker")

POLL_INTERVAL = timedelta(seconds=2)
# Latido para el healthcheck del contenedor (docker-compose): se toca en cada ciclo.
HEARTBEAT = Path(os.environ.get("WORKER_HEARTBEAT", "/tmp/worker-heartbeat"))
PURGE_INTERVAL = timedelta(hours=1)


async def purge_login_attempts(db: Database) -> int:
    async with db.transaction() as connection:
        purged = await connection.execute(text("SELECT login_attempt_purge()"))
        return int(purged.scalar_one())


async def run_once(db: Database, dispatcher: OutboxDispatcher, *, purge: bool) -> int:
    sent = await dispatcher.dispatch()
    if purge:
        await purge_login_attempts(db)
    return sent


async def main(*, once: bool) -> None:
    settings = get_settings()
    db = Database.from_url(settings.database_url, role="app_worker")
    dispatcher = OutboxDispatcher(db, email_sender_from_settings(settings))
    loop = asyncio.get_running_loop()
    last_purge: float | None = None
    try:
        while True:
            purge_due = (
                last_purge is None or loop.time() - last_purge >= PURGE_INTERVAL.total_seconds()
            )
            try:
                sent = await run_once(db, dispatcher, purge=purge_due)
            except Exception:
                # Un fallo pasajero (p. ej. de la base de datos) no tumba el trabajador.
                logger.exception("fallo en el ciclo del trabajador")
                sent = 0
            else:
                if purge_due:
                    last_purge = loop.time()
                # Solo un ciclo que funcionó cuenta como latido: con la base caída, el
                # healthcheck lo marca como no saludable.
                HEARTBEAT.touch()
            if sent:
                logger.info("correos enviados: %s", sent)
            if once:
                return
            await asyncio.sleep(POLL_INTERVAL.total_seconds())
    finally:
        await db.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trabajador de la bandeja de salida")
    parser.add_argument("--once", action="store_true", help="procesa un lote y termina")
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main(once=parser.parse_args().once))
