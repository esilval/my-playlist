"""El mando de producción de la imagen del monolito (feature 004, plan D3, D8, D11)."""

import json
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[2] / "Dockerfile"


def _command() -> str:
    [line] = [line for line in DOCKERFILE.read_text().splitlines() if line.startswith("CMD ")]
    return " ".join(json.loads(line.removeprefix("CMD ")))


def test_F004_R004_el_mando_de_la_imagen_no_migra_al_arrancar() -> None:
    command = _command()

    assert "alembic" not in command
    assert "python -m app.ops.env uvicorn app.main:app" in command
    # Los procesos de la API son los de la tarea (ADR-0015).
    assert "--workers ${API_WORKERS:-2}" in command


def test_F004_R016_el_mando_de_la_imagen_desactiva_el_registro_de_acceso_de_uvicorn() -> None:
    assert "--no-access-log" in _command()
