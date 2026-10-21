import ast
from pathlib import Path

from fastapi.testclient import TestClient

APP_DIR = Path(__file__).resolve().parents[2] / "app"
# Un dominio por módulo del monolito: accounts (C1) y sessions (C2).
DOMAIN_DIRS = (APP_DIR / "accounts" / "domain", APP_DIR / "sessions" / "domain")
FORBIDDEN_IN_DOMAIN = {"fastapi", "starlette", "sqlalchemy", "httpx", "httpx2"}


def test_app_arranca_y_responde_health(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def _imported_roots(source: Path) -> set[str]:
    tree = ast.parse(source.read_text(), filename=str(source))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_dominio_no_importa_frameworks_ni_orm() -> None:
    # S1: el dominio no depende de FastAPI, SQLAlchemy ni clientes HTTP.
    offenders = {
        str(path.relative_to(APP_DIR)): sorted(_imported_roots(path) & FORBIDDEN_IN_DOMAIN)
        for domain_dir in DOMAIN_DIRS
        for path in domain_dir.rglob("*.py")
        if _imported_roots(path) & FORBIDDEN_IN_DOMAIN
    }

    assert all(domain_dir.is_dir() for domain_dir in DOMAIN_DIRS)
    assert offenders == {}
