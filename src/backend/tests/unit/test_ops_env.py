"""Composición de las URL de conexión en el arranque (feature 004, plan D6)."""

import os

import pytest
from sqlalchemy import make_url

from app.ops import env
from app.ops.env import compose_urls

PASSWORD = "c0ntra:se@ña/con#raros"
TOKEN = "token:de@redis/raro"


def test_F004_R006_env_compone_las_url_sin_escribir_la_contrasena_en_el_registro(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    parts = {
        "DATABASE_HOST": "db.interno",
        "DATABASE_NAME": "myplaylist",
        "DATABASE_USER": "myplaylist_api",
        "DATABASE_PASSWORD": PASSWORD,
        "REDIS_HOST": "redis.interno",
        "REDIS_AUTH_TOKEN": TOKEN,
    }

    urls = compose_urls(parts)

    database = make_url(urls["DATABASE_URL"])
    assert (database.drivername, database.host, database.port) == (
        "postgresql+asyncpg",
        "db.interno",
        5432,
    )
    assert (database.username, database.password, database.database) == (
        "myplaylist_api",
        PASSWORD,
        "myplaylist",
    )
    assert urls["REDIS_URL"].startswith("rediss://:")
    assert urls["REDIS_URL"].endswith("@redis.interno:6379/0")
    # Si ya vienen dadas, como en el compose, no se tocan.
    assert compose_urls({**parts, "DATABASE_URL": "x", "REDIS_URL": "y"}) == {}
    assert compose_urls({}) == {}

    # El arranque pone las URL en el entorno y sustituye el proceso, sin escribirlas.
    launched: list[list[str]] = []
    for name in ("DATABASE_URL", "REDIS_URL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in parts.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(os, "execvp", lambda file, argv: launched.append(argv))

    env.main(["uvicorn", "app.main:app"])

    assert launched == [["uvicorn", "app.main:app"]]
    assert make_url(os.environ["DATABASE_URL"]).password == PASSWORD
    output = capsys.readouterr()
    for secret in (PASSWORD, TOKEN, "c0ntra", "token:de"):
        assert secret not in output.out + output.err
    assert "DATABASE_URL" in output.err
