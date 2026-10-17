import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.accounts.domain.data_policy import DRAFT_VERSION
from app.accounts.infrastructure.policy_files import POLICY_DIR, FilePolicyStore
from app.main import create_app
from app.shared.config import Settings
from tests.integration.conftest import BACKEND_DIR


def test_F001_R022_politica_se_sirve_sin_sesion() -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/public/data-policy")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"version", "content"}
    assert body["version"] == DRAFT_VERSION
    assert body["content"] == (POLICY_DIR / f"{DRAFT_VERSION}.md").read_text(encoding="utf-8")
    assert "set-cookie" not in response.headers


def test_F001_R022_produccion_no_arranca_con_borrador() -> None:
    env = {
        **os.environ,
        "ENV": "production",
        "EMAIL_BACKEND": "ses",
        "DATA_POLICY_VERSION": DRAFT_VERSION,
    }
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode != 0
    assert "política de tratamiento definitiva" in result.stderr

    with pytest.raises(ValidationError, match="borrador"):
        Settings(env="production", email_backend="ses", data_policy_version=DRAFT_VERSION)


def test_F001_R022_version_vigente_inexistente_impide_arrancar() -> None:
    with pytest.raises(KeyError):
        create_app(Settings(data_policy_version="2099-01"))


def test_F001_R022_sirve_la_version_configurada(tmp_path: Path) -> None:
    (tmp_path / "2026-10.md").write_text("# Política 2026-10\n", encoding="utf-8")
    store = FilePolicyStore(tmp_path)
    settings = Settings(data_policy_version="2026-10")

    with TestClient(create_app(settings, policy_store=store)) as client:
        body = client.get("/api/public/data-policy").json()

    assert body == {"version": "2026-10", "content": "# Política 2026-10\n"}


def test_almacen_de_politicas_rechaza_rutas_y_versiones_inexistentes(tmp_path: Path) -> None:
    (tmp_path / "2026-10.md").write_text("# Política 2026-10\n", encoding="utf-8")
    store = FilePolicyStore(tmp_path)

    for bad in ("../2026-10", "2026-10.md", "", "otra"):
        with pytest.raises(KeyError):
            store.get(bad)
