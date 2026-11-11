"""Configuración de los entornos desplegados (feature 004, plan D7)."""

import pytest
from pydantic import ValidationError

from app.shared.config import (
    LOCAL_DEVICE_TOKEN_SECRET,
    LOCAL_REALTIME_TICKET_SECRET,
    Settings,
    get_settings,
    settings_or_exit,
)

SECRET = "secreto-de-produccion-de-al-menos-32-caracteres"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """La configuración lee el entorno: que no influya lo que tenga exportado quien corre
    las pruebas."""
    for name in (
        "ENV",
        "EMAIL_BACKEND",
        "EMAIL_FROM",
        "PUBLIC_BASE_URL",
        "DATA_POLICY_VERSION",
        "CATALOG_PROVIDER",
        "YOUTUBE_API_KEY",
        "REALTIME_TICKET_SECRET",
        "DEVICE_TOKEN_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)


def _settings(**values: str) -> Settings:
    return Settings.model_validate({**values, "_env_file": None})


def _production(**overrides: str) -> Settings:
    return _settings(
        **{
            "env": "production",
            "email_backend": "ses",
            "email_from": "MyPlaylist <no-responder@myplaylist.200oklabs.com>",
            "public_base_url": "https://myplaylist.200oklabs.com",
            "data_policy_version": "2026-10",
            "realtime_ticket_secret": SECRET,
            "catalog_provider": "youtube",
            "youtube_api_key": "clave-de-produccion-de-pruebas",
            "device_token_secret": SECRET,
            **overrides,
        }
    )


def _preproduction(**overrides: str) -> Settings:
    return _settings(
        **{
            "env": "preproduction",
            "email_backend": "smtp",
            "public_base_url": "https://pre.myplaylist.200oklabs.com",
            "catalog_provider": "fake",
            "realtime_ticket_secret": SECRET,
            "device_token_secret": SECRET,
            **overrides,
        }
    )


def test_F004_R007_production_rechaza_un_remitente_de_example_com() -> None:
    assert _production().email_from.endswith("@myplaylist.200oklabs.com>")

    for sender in (
        "MyPlaylist <no-responder@example.com>",
        "no-responder@EXAMPLE.com",
        "no-responder@mail.example.com",
        "MyPlaylist",
        "",
    ):
        with pytest.raises(ValidationError, match="EMAIL_FROM"):
            _production(email_from=sender)


def test_F004_R007_production_rechaza_una_url_publica_sin_https_o_localhost() -> None:
    assert _production().public_base_url == "https://myplaylist.200oklabs.com"

    for url in (
        "http://myplaylist.200oklabs.com",
        "http://localhost:5173",
        "https://localhost",
        "https://127.0.0.1:8443",
        "https://0.0.0.0",
        "https://",
        "myplaylist.200oklabs.com",
    ):
        with pytest.raises(ValidationError, match="PUBLIC_BASE_URL"):
            _production(public_base_url=url)


def test_F004_R007_preproduction_exige_secretos_propios() -> None:
    for secret in (LOCAL_REALTIME_TICKET_SECRET, "", "corto"):
        with pytest.raises(ValidationError, match="REALTIME_TICKET_SECRET") as error:
            _preproduction(realtime_ticket_secret=secret)
        assert "preproduction" in str(error.value)
    for secret in (LOCAL_DEVICE_TOKEN_SECRET, "", "corto"):
        with pytest.raises(ValidationError, match="DEVICE_TOKEN_SECRET") as error:
            _preproduction(device_token_secret=secret)
        assert "preproduction" in str(error.value)


def test_F004_R022_preproduction_admite_el_catalogo_falso_smtp_y_la_politica_en_borrador() -> None:
    settings = _preproduction()

    assert settings.env == "preproduction"
    assert settings.catalog_provider == "fake"
    assert settings.email_backend == "smtp"
    assert settings.data_policy_version == "0000-borrador"
    # Las comprobaciones del remitente y la URL pública son solo de producción.
    assert _preproduction(email_from="MyPlaylist <no-responder@example.com>").env == (
        "preproduction"
    )


def test_F004_R016_settings_or_exit_escribe_solo_los_mensajes_y_termina_con_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    visible = "secreto-del-ticket-que-no-debe-aparecer-en-el-registro"
    for name, value in {
        "ENV": "production",
        "EMAIL_BACKEND": "ses",
        "DATA_POLICY_VERSION": "2026-10",
        "REALTIME_TICKET_SECRET": visible,
        "CATALOG_PROVIDER": "youtube",
        "YOUTUBE_API_KEY": "clave-de-youtube-que-no-debe-aparecer",
        "DEVICE_TOKEN_SECRET": "corto",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    try:
        with pytest.raises(SystemExit) as exit_info:
            settings_or_exit()
    finally:
        get_settings.cache_clear()

    assert exit_info.value.code == 1
    # Sin el error de pydantic encadenado, que lleva la entrada.
    assert exit_info.value.__suppress_context__ is True
    err = capsys.readouterr().err
    assert err.startswith("configuración inválida: ")
    assert "DEVICE_TOKEN_SECRET" in err
    for value in (visible, "clave-de-youtube-que-no-debe-aparecer", "'corto'"):
        assert value not in err

    # Con una configuración válida, la devuelve.
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setenv("CATALOG_PROVIDER", "fake")
    try:
        assert settings_or_exit().env == "local"
    finally:
        get_settings.cache_clear()
