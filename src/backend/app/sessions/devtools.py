"""Herramienta de desarrollo: agregar canciones a la cola (plan D9).

Con esta feature no hay forma de que una canción entre en la cola: los pedidos llegan
con B03. Esta herramienta lo hace a mano para la demo local y las pruebas e2e:

    docker compose exec api python -m app.sessions.devtools enqueue \\
        --email dueno@ejemplo.com --title "Canción" --ref fake:3s

Usa el mismo caso de uso que usará B03 (publica `queue.changed`). Se niega a correr
con ENV=production.
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence

from app.accounts.domain.registration import normalize_email
from app.accounts.infrastructure.repositories import SqlAccountsUnitOfWork
from app.sessions.infrastructure.redis_publisher import RedisEventPublisher
from app.sessions.infrastructure.repositories import SqlSessionsUnitOfWork
from app.sessions.interface import EnqueueTrack, NoOpenSession
from app.shared.config import Settings, get_settings
from app.shared.db import Database


class ProductionRefused(Exception):
    """La herramienta no corre en producción."""


async def enqueue(settings: Settings, *, email: str, title: str, ref: str) -> str:
    if settings.env == "production":
        raise ProductionRefused
    db = Database.from_url(settings.database_url, role="app_api")
    publisher = RedisEventPublisher.from_url(settings.redis_url)
    try:
        # Como main.py, la herramienta compone C1 y C2: busca el establecimiento del
        # propietario por su correo y agrega la canción por la interfaz de C2.
        async with SqlAccountsUnitOfWork(db)() as accounts:
            owner = await accounts.find_owner_by_email(normalize_email(email))
        if owner is None:
            raise LookupError(f"no hay ninguna cuenta con el correo {email}")
        add = EnqueueTrack(unit_of_work=SqlSessionsUnitOfWork(db), publisher=publisher)
        item = await add(owner.establishment_id, ref, title)
        return f"«{item.title}» en la posición {item.position}"
    finally:
        await publisher.aclose()
        await db.dispose()


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.sessions.devtools")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("enqueue", help="agrega una canción a la sesión abierta")
    add.add_argument("--email", required=True, help="correo del propietario")
    add.add_argument("--title", required=True)
    add.add_argument("--ref", required=True, help="referencia del proveedor, p. ej. fake:3s")
    args = parser.parse_args(argv)

    try:
        result = asyncio.run(
            enqueue(settings or get_settings(), email=args.email, title=args.title, ref=args.ref)
        )
    except ProductionRefused:
        print("devtools no corre con ENV=production", file=sys.stderr)
        return 2
    except NoOpenSession:
        print("ese establecimiento no tiene una sesión de música abierta", file=sys.stderr)
        return 1
    except (LookupError, ValueError) as error:
        # Correo sin cuenta, o título o referencia vacíos.
        print(error, file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
