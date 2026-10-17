"""Configuración del monolito, leída de variables de entorno."""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["local", "test", "production"] = "local"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/myplaylist"
    # Argon2id (plan D3), fijado con perf/accounts.js (T023): la configuración mínima de
    # OWASP (19 MiB, 2 pasadas, 1 hilo), unos 20 ms por hash. Con los 150 ms de partida
    # (64 MiB, 3 pasadas), 50 registros a la vez daban p95 de 4,9 s en local.
    argon2_time_cost: int = 2
    argon2_memory_cost_kib: int = 19456
    argon2_parallelism: int = 1
    # Correo (ADR-0011): SES en AWS; SMTP contra Mailpit en local; memoria en pruebas.
    email_backend: Literal["ses", "smtp", "memory"] = "smtp"
    # El dominio real del remitente (con SPF, DKIM y DMARC) aún no está decidido.
    email_from: str = "MyPlaylist <no-responder@example.com>"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    aws_region: str = "us-east-1"
    # Versión vigente de la política de tratamiento (plan D12); la de borrador hasta que
    # llegue el texto del negocio.
    data_policy_version: str = "0000-borrador"
    # Origen público de la SPA: enlaces de los correos y URL del QR (plan D1, D10).
    public_base_url: str = "http://localhost:5173"

    @model_validator(mode="after")
    def _production_sends_with_ses(self) -> "Settings":
        if self.env == "production" and self.email_backend != "ses":
            raise ValueError("en producción el correo se envía con SES (ADR-0011)")
        if self.env == "production" and self.data_policy_version == "0000-borrador":
            raise ValueError(
                "en producción hace falta la política de tratamiento definitiva (R022): "
                "la versión vigente es el borrador"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
