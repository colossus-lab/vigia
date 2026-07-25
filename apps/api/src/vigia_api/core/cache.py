"""Cache TTL en memoria para agregaciones caras (dashboard, COUNT del feed).

La API corre en un solo proceso uvicorn (ver `apps/api/Dockerfile`), así que un
dict alcanza: no hace falta Redis ni sumar dependencias. Si algún día se escala
a N workers, el peor caso son N misses por ventana de TTL, no incoherencia.

El lock por clave evita la estampida: sin él, K requests concurrentes al
dashboard disparan K seq scans de 543k filas en vez de uno.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

# clave -> (vence_en_monotonic, valor)
_store: dict[str, tuple[float, Any]] = {}
_locks: dict[str, asyncio.Lock] = {}

# Techo defensivo: las claves son combinaciones de filtros (acotadas en la
# práctica), pero vienen de query params, así que no las dejamos crecer solas.
_MAX_ENTRIES = 512


def _purge_expired(now: float) -> None:
    for k in [k for k, (exp, _) in _store.items() if exp <= now]:
        _store.pop(k, None)
        _locks.pop(k, None)


async def cached(key: str, ttl: float, factory: Callable[[], Awaitable[Any]]) -> Any:
    """Devuelve el valor cacheado o lo calcula con `factory` y lo guarda `ttl` seg."""
    now = time.monotonic()
    hit = _store.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        # Otro request pudo haberlo poblado mientras esperábamos el lock.
        hit = _store.get(key)
        if hit is not None and hit[0] > time.monotonic():
            return hit[1]
        value = await factory()
        if len(_store) >= _MAX_ENTRIES:
            _purge_expired(time.monotonic())
        _store[key] = (time.monotonic() + ttl, value)
        return value


def invalidate(prefix: str = "") -> None:
    """Descarta las entradas cuya clave arranca con `prefix` (todas si es "")."""
    for k in [k for k in _store if k.startswith(prefix)]:
        _store.pop(k, None)
        _locks.pop(k, None)
