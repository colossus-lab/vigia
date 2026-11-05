from __future__ import annotations

import os
import ssl
from typing import Any
from urllib.parse import urlsplit

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter


#: Hosts que no responden desde AWS y sí desde cualquier IP argentina.
#:
#: Medido 2026-11-05 (ver CLAUDE.md, "Geo-bloqueo BORA + datos.hcdn"): el
#: Boletín Oficial descarta los paquetes en 443 y 80, y el CKAN de Diputados
#: resetea el TLS apenas llega el ClientHello. No es la IP del EC2 ni AWS:
#: sondas en EE.UU., Alemania y Brasil reciben lo mismo, y desde Argentina los
#: dos responden 200. Estos hosts —y solo estos— salen por el proxy argentino
#: (`VIGIA_PROXY_AR`, el mismo VPS que usa Licitar). El alcance es POR HOST a
#: propósito: el VPS es chico, y mandarle InfoLEG entero lo convertiría en el
#: cuello de botella de toda la ingesta. `www.hcdn.gob.ar` (misma IP que
#: `datos.`, otro vhost) sigue respondiendo directo y por eso no está acá.
_PROXY_AR_POR_HOST: frozenset[str] = frozenset(
    {
        "www.boletinoficial.gob.ar",
        "datos.hcdn.gob.ar",
    }
)

#: Variable de entorno con el proxy de salida argentino, como URL con
#: credenciales: `http://usuario:clave@host:8888`. Vive en `.env.production`
#: del EC2 (los dos workers lo leen por `env_file`).
ENV_PROXY_AR = "VIGIA_PROXY_AR"

#: Valor especial: "no hace falta proxy, YA estoy en Argentina" (dev local, o
#: una ingesta a mano desde una máquina argentina). Tiene que ser explícito y no
#: un default: un worker de producción con la variable sin setear tiene que
#: fallar ruidosamente en vez de salir directo desde AWS.
PROXY_AR_DIRECTO = "direct"


class ProxyArNoConfigurado(RuntimeError):
    """El host necesita salida argentina y `VIGIA_PROXY_AR` no está.

    Se levanta al CONSTRUIR el client, antes del primer request. Preferimos que
    la task reviente con un mensaje que diga qué falta a que haga el request
    directo desde AWS: ese request no falla rápido — se come 60 s de timeout
    por intento, tres intentos por página, y la fuente queda en `error` con
    un `ConnectTimeout` que no dice nada de la causa.
    """


def _proxy_para(base_url: str) -> str | None:
    """URL del proxy si el host lo necesita; `None` para salir directo.

    Lee el entorno en cada llamada y no al importar: `make_client` se llama al
    instanciar cada client, así que un worker recién levantado toma la variable
    del contenedor, y los tests pueden setearla con `monkeypatch` sin recargar
    el módulo.
    """
    host = (urlsplit(base_url).hostname or "").lower()
    if host not in _PROXY_AR_POR_HOST:
        return None
    valor = os.environ.get(ENV_PROXY_AR, "").strip()
    if not valor:
        raise ProxyArNoConfigurado(
            f"{host} necesita salida desde una IP argentina y {ENV_PROXY_AR} no "
            f"está configurada. Poné la URL del proxy AR (http://usuario:clave@"
            f"host:puerto; ver infra/DEPLOY.md, 'Salida argentina'), o "
            f"{ENV_PROXY_AR}={PROXY_AR_DIRECTO} si esta máquina ya está en "
            f"Argentina."
        )
    if valor.lower() == PROXY_AR_DIRECTO:
        return None
    return valor


def make_client(
    *,
    base_url: str,
    timeout: float = 15.0,
    verify_ssl: bool = True,
    headers: dict[str, str] | None = None,
) -> httpx.AsyncClient:
    verify: bool | ssl.SSLContext = True
    if not verify_ssl:
        verify = False
    # El proxy tuneliza el TLS con CONNECT: la verificación del certificado se
    # sigue haciendo contra el portal, no contra el VPS.
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        verify=verify,
        headers=headers or {"User-Agent": "vigia/0.1 (+https://vigia.legal)"},
        follow_redirects=True,
        proxy=_proxy_para(base_url),
    )


async def get_json(client: httpx.AsyncClient, path: str, **kwargs: Any) -> Any:
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.5, max=4),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        reraise=True,
    ):
        with attempt:
            resp = await client.get(path, **kwargs)
            resp.raise_for_status()
            return resp.json()
    raise RuntimeError("unreachable")


async def get_text(client: httpx.AsyncClient, path: str, **kwargs: Any) -> str:
    """GET con el mismo retry que get_json, devolviendo el body como texto (HTML)."""
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.5, max=4),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        reraise=True,
    ):
        with attempt:
            resp = await client.get(path, **kwargs)
            resp.raise_for_status()
            return resp.text
    raise RuntimeError("unreachable")
