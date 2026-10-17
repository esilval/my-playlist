"""Política de tratamiento guardada como archivos Markdown por versión (plan D12)."""

from pathlib import Path

from app.accounts.domain.data_policy import DataPolicy

POLICY_DIR = Path(__file__).resolve().parents[1] / "policy"


class FilePolicyStore:
    def __init__(self, directory: Path = POLICY_DIR) -> None:
        self._directory = directory

    def get(self, version: str) -> DataPolicy:
        # La versión sale de la configuración, pero se valida igual: nada de rutas.
        path = self._directory / f"{version}.md"
        if path.parent != self._directory or not path.is_file():
            raise KeyError(version)
        return DataPolicy(version=version, content=path.read_text(encoding="utf-8"))
