"""Configuración del catálogo y del secreto del dispositivo (feature 003, plan D8)."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.catalog.infrastructure.fake import FakeCatalog
from app.catalog.infrastructure.youtube import YouTubeCatalog
from app.main import create_app
from app.shared.config import LOCAL_DEVICE_TOKEN_SECRET, Settings

SECRET = "secreto-de-produccion-de-al-menos-32-caracteres"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """La configuración lee el entorno: que no influya lo que tenga exportado quien corre
    las pruebas."""
    for name in ("ENV", "CATALOG_PROVIDER", "YOUTUBE_API_KEY", "DEVICE_TOKEN_SECRET"):
        monkeypatch.delenv(name, raising=False)


def _production(**overrides: str) -> Settings:
    values = {
        "env": "production",
        "email_backend": "ses",
        "data_policy_version": "2026-10",
        "realtime_ticket_secret": SECRET,
        "catalog_provider": "youtube",
        "youtube_api_key": "clave-de-produccion-de-pruebas",
        "device_token_secret": SECRET,
        **overrides,
    }
    return Settings.model_validate({**values, "_env_file": None})


def test_F003_R003_en_local_el_catalogo_es_el_falso() -> None:
    settings = Settings(_env_file=None)
    assert settings.catalog_provider == "fake"

    # Dentro del cliente de pruebas, para que el lifespan cierre Redis y YouTube.
    with TestClient(create_app(settings)) as client:
        state = client.app.state  # type: ignore[attr-defined]
        assert isinstance(state.search_tracks.catalog, FakeCatalog)
        assert isinstance(state.track_lookup.catalog, FakeCatalog)

    # Con YouTube y su clave, el catálogo es el de YouTube (también en local, para probar).
    youtube = Settings(_env_file=None, catalog_provider="youtube", youtube_api_key="clave-local")
    with TestClient(create_app(youtube)) as client:
        state = client.app.state  # type: ignore[attr-defined]
        assert isinstance(state.search_tracks.catalog, YouTubeCatalog)
        assert state.request_track.lookup is state.track_lookup


def test_F003_R003_produccion_no_arranca_sin_clave_de_youtube_o_con_el_catalogo_falso() -> None:
    assert _production().catalog_provider == "youtube"

    with pytest.raises(ValidationError, match="CATALOG_PROVIDER=youtube"):
        _production(catalog_provider="fake")
    for key in ("", "   "):
        with pytest.raises(ValidationError, match="YOUTUBE_API_KEY"):
            _production(youtube_api_key=key)
    # También en local, YouTube sin clave no arranca.
    with pytest.raises(ValidationError, match="YOUTUBE_API_KEY"):
        Settings(_env_file=None, catalog_provider="youtube")


def test_F003_R002_produccion_no_arranca_con_el_secreto_de_dispositivo_de_desarrollo() -> None:
    for secret in (LOCAL_DEVICE_TOKEN_SECRET, "", "corto"):
        with pytest.raises(ValidationError, match="DEVICE_TOKEN_SECRET"):
            _production(device_token_secret=secret)

    assert _production(device_token_secret="x" * 32).device_token_secret == "x" * 32
