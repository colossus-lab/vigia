from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valores que NO pueden usarse como secreto real. El default de abajo vive en un
# repo público: si la env var faltara, la API firmaría y verificaría los JWT con
# un secreto que cualquiera puede leer en GitHub.
_SECRETOS_PROHIBIDOS = {"", "dev-only-change-me", "change-me", "changeme", "secret", "test"}
_SECRETO_LARGO_MINIMO = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://vigia:vigia@localhost:5432/vigia"
    redis_url: str = "redis://localhost:6379/0"
    api_cors_origins: str = "http://localhost:3000"

    # Fase 2 — auth (placeholders; se activan al construir el módulo de auth).
    auth_secret: str = "dev-only-change-me"
    auth_jwt_alg: str = "HS256"
    auth_jwt_ttl_seconds: int = 60 * 60 * 24  # 24h
    auth_enabled: bool = False  # False = modo demo abierto

    # Free trial: días de uso pleno desde la creación del workspace. Al vencer,
    # los endpoints gated devuelven 402 trial_expired salvo plan != "free".
    trial_days: int = 30

    # /docs, /redoc y /openapi.json. Default False a propósito: publican el mapa
    # completo de la API (rutas gateadas, forma de los payloads) y en producción
    # no le sirven a nadie. Se prende explícito en dev con VIGIA_DOCS=true; si la
    # variable falta, quedan cerrados — que es el lado seguro del error.
    vigia_docs: bool = False

    # Rate limiting de los endpoints que mutan o son caros (ver core/ratelimit).
    # Se puede apagar por env var sin redeploy si alguna cuota resulta molesta en
    # producción; el default es prendido.
    ratelimit_enabled: bool = True

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _validar_secreto(self) -> Settings:
        """Aborta el arranque si se prende auth con un secreto que no sirve.

        `auth_secret` firma los JWT de usuario y además autentica el canal
        interno web→API. Con auth prendida y un secreto débil o placeholder,
        cualquiera puede forjar un token para cualquier email. Preferimos que la
        API no arranque antes que arrancar insegura.
        """
        if not self.auth_enabled:
            return self
        secreto = self.auth_secret.strip()
        if secreto.lower() in _SECRETOS_PROHIBIDOS:
            raise ValueError(
                "AUTH_SECRET es un placeholder o está vacío y AUTH_ENABLED=true. "
                "Generá uno real: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if len(secreto) < _SECRETO_LARGO_MINIMO:
            raise ValueError(
                f"AUTH_SECRET tiene {len(secreto)} caracteres; el mínimo es "
                f"{_SECRETO_LARGO_MINIMO} con AUTH_ENABLED=true."
            )
        return self


def get_settings() -> Settings:
    return Settings()
