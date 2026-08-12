"""Rate limiting en memoria para los endpoints que mutan o son caros.

Mismo criterio que `core.cache`: la API corre en un solo proceso uvicorn (ver
`apps/api/Dockerfile`), así que un dict alcanza y no hace falta sumar Redis como
dependencia. Si algún día se escala a N workers, el límite efectivo se multiplica
por N — hay que mover esto a un store compartido antes de agregar `--workers`.

Ventana deslizante (una cola de timestamps por clave) en vez de ventana fija:
con cuotas chicas el costo de memoria es trivial y evita el clásico agujero del
borde, donde 2× la cuota entra en dos segundos a caballo de dos ventanas.

NO se limita nada de lectura pública (`/normas`, `/search`, `/stats`, `/avisos`):
el SSR de Vercel llega desde un puñado de IPs de AWS y un límite por IP ahí
estrangularía el sitio entero. Ver `ratelimit_por_ip` para el mismo problema en
`/auth/sync`, que también llega desde Vercel.
"""
from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status

from vigia_api.core.apikeys import ApiClient, current_api_client
from vigia_api.core.security import WorkspaceContext, current_workspace
from vigia_api.core.settings import Settings, get_settings

# clave -> timestamps (monotonic) de los hits dentro de la ventana
_hits: dict[str, deque[float]] = {}

# clave -> (día UTC, consumidos). Para cuotas diarias: guardar una cola de N mil
# timestamps por key sería memoria tirada cuando alcanza con un contador.
_diarios: dict[str, tuple[str, int]] = {}

# Techo defensivo. Las claves son IPs o ids de workspace, acotadas en la
# práctica, pero vienen de afuera: no las dejamos crecer sin límite.
_MAX_CLAVES = 10_000


def _purgar(ahora: float) -> None:
    """Descarta las claves cuya cola quedó vacía. O(n) pero corre rara vez."""
    for k in [k for k, dq in _hits.items() if not dq]:
        _hits.pop(k, None)


def _podar(dq: deque[float], ahora: float, ventana: float) -> None:
    while dq and dq[0] <= ahora - ventana:
        dq.popleft()


def consultar(clave: str, limite: int, ventana: float) -> float | None:
    """¿Está pasado de cuota? Devuelve segundos a esperar, o None si puede pasar.

    NO registra el hit: sirve para chequear antes de hacer el trabajo.
    """
    ahora = time.monotonic()
    dq = _hits.get(clave)
    if dq is None:
        return None
    _podar(dq, ahora, ventana)
    if len(dq) < limite:
        return None
    return max(0.0, dq[0] + ventana - ahora)


def registrar(clave: str, ventana: float) -> None:
    """Anota un hit contra la clave."""
    ahora = time.monotonic()
    dq = _hits.get(clave)
    if dq is None:
        if len(_hits) >= _MAX_CLAVES:
            _purgar(ahora)
        dq = _hits.setdefault(clave, deque())
    _podar(dq, ahora, ventana)
    dq.append(ahora)


def consumir(clave: str, limite: int, ventana: float) -> float | None:
    """Consulta y, si puede pasar, registra el hit. Devuelve espera o None."""
    espera = consultar(clave, limite, ventana)
    if espera is not None:
        return espera
    registrar(clave, ventana)
    return None


def segundos_hasta_reset_diario(ahora: datetime | None = None) -> int:
    """Segundos hasta las 00:00 UTC, cuando se reinician las cuotas diarias."""
    ahora = ahora or datetime.now(timezone.utc)
    manana = (ahora + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((manana - ahora).total_seconds()))


def consumir_diario(clave: str, limite: int) -> tuple[int, int] | None:
    """Cuota por día calendario UTC. Devuelve `(restante, seg_hasta_reset)` o None.

    Día calendario y no ventana deslizante de 24h porque del otro lado hay una
    persona leyendo "20.000 por día": que el reset sea a las 00:00 UTC se explica
    en una línea y se puede poner en un header. El agujero clásico de la ventana
    fija —2× la cuota a caballo del borde— lo tapa el límite por minuto, que va
    en la misma dependency.

    O(1) en memoria: un contador por clave, no la cola de timestamps que usa
    `consumir`. Se pierde al reiniciar la API; es una cuota de cortesía, no
    facturación.
    """
    ahora = datetime.now(timezone.utc)
    hoy = ahora.date().isoformat()
    reset = segundos_hasta_reset_diario(ahora)

    dia, usados = _diarios.get(clave, (hoy, 0))
    if dia != hoy:
        usados = 0
    if usados >= limite:
        return None
    if len(_diarios) >= _MAX_CLAVES and clave not in _diarios:
        for k, (d, _) in list(_diarios.items()):
            if d != hoy:
                _diarios.pop(k, None)
    _diarios[clave] = (hoy, usados + 1)
    return limite - usados - 1, reset


def reset() -> None:
    """Limpia los contadores. Para los tests: el estado es de módulo y se filtra."""
    _hits.clear()
    _diarios.clear()


def rechazar(espera: float, detalle: str) -> HTTPException:
    """429 con Retry-After, en el formato de error del resto de la API."""
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detalle,
        headers={"Retry-After": str(max(1, int(espera + 0.5)))},
    )


def client_ip(request: Request | None) -> str | None:
    """IP real del cliente. Fuente única de verdad para audit log y límites.

    Toma el PRIMER elemento de `X-Forwarded-For` y eso es seguro **porque Caddy
    reemplaza el header, no lo apendea**: verificado empíricamente contra
    caddy:2 v2.11.4 (la misma versión que corre en el EC2) con la misma forma de
    config — mandando `X-Forwarded-For: 1.2.3.4` el upstream recibe únicamente la
    IP real del peer. Sin `trusted_proxies` configurado, Caddy descarta lo que
    venga del cliente. Tampoco pasan `X-Real-IP` ni `Forwarded`.

    OJO: esa garantía se rompe si algún día se pone otro proxy o CDN por delante
    de Caddy, o si se configura `trusted_proxies`. En ese caso el primer elemento
    pasa a ser controlado por el atacante y hay que tomar el último.

    Fallback a `request.client.host` para dev local, donde no hay Caddy.
    """
    if request is None:
        return None
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None


# --- dependencies -----------------------------------------------------------
#
# Se cablean como dependencies de FastAPI, NO como middleware, y eso es a
# propósito: Starlette inserta cada `add_middleware` al principio de la pila, así
# que un limiter agregado después de `CORSMiddleware` en main.py quedaría por
# FUERA y sus 429 saldrían sin headers CORS — el browser vería un error de red
# opaco en vez de un 429 legible. Una HTTPException desde una dependency la
# maneja `ExceptionMiddleware`, que corre por DENTRO de CORS.


def limitar_por_ip(nombre: str, limite: int, ventana: float):
    """Dependency: acota `limite` requests por `ventana` segundos y por IP."""

    async def _dep(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
    ) -> None:
        # Vía Depends y no llamando get_settings() directo: `Settings()` relee el
        # .env del disco en cada construcción, y FastAPI cachea la dependency
        # dentro del request, así que se comparte con la que ya pide el resto.
        if settings is not None and not settings.ratelimit_enabled:
            return
        ip = client_ip(request) or "desconocida"
        espera = consumir(f"{nombre}:ip:{ip}", limite, ventana)
        if espera is not None:
            raise rechazar(espera, "rate_limited")

    return _dep


def limitar_por_workspace(nombre: str, limite: int, ventana: float):
    """Dependency: acota por workspace. Para endpoints ya autenticados.

    Por workspace y no por IP porque el abuso acá es de una cuenta, no de una
    red: el mismo workspace detrás de NAT corporativo comparte IP con gente que
    no tiene nada que ver.
    """

    async def _dep(
        ctx: Annotated[WorkspaceContext, Depends(current_workspace)],
        settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
    ) -> WorkspaceContext:
        if settings is not None and not settings.ratelimit_enabled:
            return ctx
        espera = consumir(f"{nombre}:ws:{ctx.workspace_id}", limite, ventana)
        if espera is not None:
            raise rechazar(espera, "rate_limited")
        return ctx

    return _dep


def limitar_por_apikey(nombre: str):
    """Dependency de `/v1`: cuota por API key, con headers para el integrador.

    Por key y no por IP: el que integra puede estar detrás de un NAT, de Lambda o
    de una IP que cambia en cada deploy, y la unidad de abuso acá es la
    credencial. En modo demo (sin key) no se limita nada.

    Los `X-RateLimit-*` no son decorativos: sin ellos el integrador descubre la
    cuota chocándose contra un 429 en producción.
    """

    async def _dep(
        response: Response,
        cliente: Annotated[ApiClient, Depends(current_api_client)],
        settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
    ) -> ApiClient:
        if settings is None or not settings.ratelimit_enabled or cliente.es_demo:
            return cliente

        por_minuto = settings.apikey_rate_por_minuto
        por_dia = settings.apikey_rate_por_dia

        espera = consumir(f"{nombre}:key:{cliente.api_key_id}:min", por_minuto, 60.0)
        if espera is not None:
            raise rechazar(espera, "rate_limited")

        cuota = consumir_diario(f"{nombre}:key:{cliente.api_key_id}:dia", por_dia)
        if cuota is None:
            raise rechazar(segundos_hasta_reset_diario(), "cuota_diaria_agotada")
        restante, reset_en = cuota
        response.headers["X-RateLimit-Limit"] = str(por_dia)
        response.headers["X-RateLimit-Remaining"] = str(restante)
        response.headers["X-RateLimit-Reset"] = str(reset_en)
        return cliente

    return _dep


def limitar_por_usuario(nombre: str, limite: int, ventana: float):
    """Dependency: acota por usuario. Para acciones destructivas sobre la cuenta."""

    async def _dep(
        ctx: Annotated[WorkspaceContext, Depends(current_workspace)],
        settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
    ) -> WorkspaceContext:
        if settings is not None and not settings.ratelimit_enabled:
            return ctx
        espera = consumir(f"{nombre}:user:{ctx.user_id}", limite, ventana)
        if espera is not None:
            raise rechazar(espera, "rate_limited")
        return ctx

    return _dep
