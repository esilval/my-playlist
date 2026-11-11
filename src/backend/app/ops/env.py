"""Arranque de los servicios en AWS: `python -m app.ops.env <mando> …` (feature 004, D6).

ECS inyecta las partes de la conexión por separado (el anfitrión y el nombre de la base,
el usuario y su contraseña desde Secrets Manager; el anfitrión de Redis y su token). Este
arranque compone con ellas `DATABASE_URL` y `REDIS_URL`, las pone en el entorno y
sustituye el proceso por el mando, sin escribir la contraseña en ningún sitio. Si
`DATABASE_URL` o `REDIS_URL` ya vienen dadas, como en el compose, no las toca.
"""

import os
import sys
from collections.abc import Mapping
from urllib.parse import quote


def compose_urls(environ: Mapping[str, str]) -> dict[str, str]:
    """Las URL que faltan y se pueden componer con las partes del entorno."""
    urls: dict[str, str] = {}
    if not environ.get("DATABASE_URL") and environ.get("DATABASE_HOST"):
        user = quote(environ.get("DATABASE_USER", ""), safe="")
        password = quote(environ.get("DATABASE_PASSWORD", ""), safe="")
        port = environ.get("DATABASE_PORT", "5432")
        name = quote(environ.get("DATABASE_NAME", "myplaylist"), safe="")
        urls["DATABASE_URL"] = (
            f"postgresql+asyncpg://{user}:{password}@{environ['DATABASE_HOST']}:{port}/{name}"
        )
    if not environ.get("REDIS_URL") and environ.get("REDIS_HOST"):
        token = environ.get("REDIS_AUTH_TOKEN", "")
        credentials = f":{quote(token, safe='')}@" if token else ""
        port = environ.get("REDIS_PORT", "6379")
        # ElastiCache cifra en tránsito (plan D4): con TLS, el esquema es rediss.
        urls["REDIS_URL"] = f"rediss://{credentials}{environ['REDIS_HOST']}:{port}/0"
    return urls


def main(argv: list[str]) -> None:
    if not argv:
        sys.stderr.write("uso: python -m app.ops.env <mando> [argumentos…]\n")
        raise SystemExit(2)
    composed = compose_urls(os.environ)
    os.environ.update(composed)
    # Solo los nombres, nunca los valores: llevan la contraseña.
    if composed:
        sys.stderr.write(f"compuestas: {', '.join(sorted(composed))}\n")
    os.execvp(argv[0], argv)


if __name__ == "__main__":
    main(sys.argv[1:])
