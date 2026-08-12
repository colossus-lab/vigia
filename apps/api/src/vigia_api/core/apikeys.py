"""Emisión y verificación de API keys — la credencial de `/v1`.

Convive con el JWT de sesión de `core.security` en vez de reemplazarlo: son dos
públicos distintos. El JWT lo emite el web tras Google OAuth, dura 24h y viaja
por el BFF; la key la pega un script de otro, no expira sola y se puede revocar
sin desloguear a nadie. Se distinguen por el prefijo del token, así que un
`Authorization: Bearer` sirve para los dos sin ambigüedad.

**Del secreto solo se guarda su SHA-256.** No es un password: es un secreto
aleatorio de 256 bits generado por nosotros, así que no hay diccionario ni
patrón humano que atacar, y un KDF lento (bcrypt, argon2) no compraría nada —
costaría latencia en cada request de la API pública. Lo que sí importa es que el
hash tenga índice único, para que verificar una key sea un lookup.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select, update

from vigia_api.core.db import get_sessionmaker
from vigia_api.core.settings import Settings, get_settings
from vigia_shared.models import ApiKey

# Prefijo fijo, para que una key filtrada sea reconocible de un vistazo (en un
# repo, un log, un pastebin) y los escáneres de secretos la puedan detectar.
PREFIJO = "vg_live_"

# Cuántos caracteres del secreto se guardan en claro para poder listarlo.
_LARGO_PREFIJO_VISIBLE = len(PREFIJO) + 6


def hashear(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generar() -> tuple[str, str, str]:
    """Devuelve `(secreto, prefijo_visible, hash)`. El secreto no se persiste."""
    # 32 bytes → 43 chars url-safe. Sin caracteres que se rompan al copiar de una
    # terminal o al meterlos en una env var.
    secreto = PREFIJO + secrets.token_urlsafe(32)
    return secreto, secreto[:_LARGO_PREFIJO_VISIBLE], hashear(secreto)


@dataclass(frozen=True)
class ApiClient:
    """Quién está llamando a `/v1`."""

    workspace_id: int
    api_key_id: int | None  # None solo en modo demo (auth apagada)
    name: str | None

    @property
    def es_demo(self) -> bool:
        return self.api_key_id is None


_DEMO = ApiClient(workspace_id=0, api_key_id=None, name="demo")


# `last_used_at` es telemetría, no contabilidad: escribirlo en cada request
# sumaría un UPDATE por request a la API pública. Se anota como mucho una vez
# cada `_INTERVALO_USO` por key, con el último instante escrito en memoria.
_INTERVALO_USO = 300.0
_ultimo_uso: dict[int, float] = {}


def _debe_anotar_uso(api_key_id: int) -> bool:
    ahora = time.monotonic()
    previo = _ultimo_uso.get(api_key_id)
    if previo is not None and ahora - previo < _INTERVALO_USO:
        return False
    _ultimo_uso[api_key_id] = ahora
    return True


def reset_memo_uso() -> None:
    """Limpia el memo de `last_used_at`. Para los tests: el estado es de módulo."""
    _ultimo_uso.clear()


def _no_autorizado(detalle: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detalle,
        headers={"WWW-Authenticate": 'Bearer realm="vigia-api"'},
    )


def _extraer_token(authorization: str | None) -> str:
    if not authorization:
        raise _no_autorizado("missing_api_key")
    esquema, _, resto = authorization.partition(" ")
    if esquema.lower() != "bearer" or not resto.strip():
        raise _no_autorizado("missing_api_key")
    token = resto.strip()
    if not token.startswith(PREFIJO):
        # El caso real: alguien pega el JWT de sesión del web contra /v1. El
        # detalle lo dice en vez de devolver un "invalid" genérico que manda a
        # buscar el problema en el lado equivocado.
        raise _no_autorizado("no_es_una_api_key")
    return token


async def current_api_client(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> ApiClient:
    """Dependency de `/v1`: resuelve la key a un workspace, o 401.

    Con `auth_enabled=False` (modo demo, el default en dev) deja pasar sin key,
    igual que hace `current_workspace` con la sesión: si no, levantar el stack
    local obligaría a sembrar un workspace y emitir una credencial antes de
    poder pegarle a un endpoint público.
    """
    if not settings.auth_enabled:
        return _DEMO

    token = _extraer_token(authorization)
    Session = get_sessionmaker()
    async with Session() as session:
        fila = (
            await session.execute(select(ApiKey).where(ApiKey.token_hash == hashear(token)))
        ).scalar_one_or_none()
        if fila is None:
            raise _no_autorizado("invalid_api_key")
        if fila.revoked_at is not None:
            # Distinguirla de una key inexistente le ahorra a un integrador
            # horas de debug del lado equivocado, y para llegar hasta acá ya
            # tuvo que presentar el secreto correcto.
            raise _no_autorizado("api_key_revocada")

        if _debe_anotar_uso(fila.id):
            await session.execute(
                update(ApiKey)
                .where(ApiKey.id == fila.id)
                .values(last_used_at=datetime.now(timezone.utc))
            )
            await session.commit()

    return ApiClient(workspace_id=fila.workspace_id, api_key_id=fila.id, name=fila.name)
