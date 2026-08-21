"""Helpers compartidos por los tests de la API.

`rutas_de` existe por un cambio de FastAPI que rompió en silencio a varios
tests a la vez: desde 0.141 `include_router` **no aplana** las rutas en el
momento. Deja un `_IncludedRouter` en `app.routes` y las resuelve tarde, así
que enumerar con `getattr(r, "path", None)` devolvía `None` para todo lo que
viene de un router incluido — o sea, para casi toda la API.

Los tests que dependían de eso (RBAC, gating de `/v1`, hardening) no fallaban:
pasaban **en falso**, porque un `set()` vacío hace que cualquier "no hay
endpoint sin protección" sea trivialmente cierto. Se detectó recién al sumar
`apps/api/tests` al CI, que instala las versiones más nuevas.

Cubre las dos formas para que los tests corran igual con la versión pineada
del venv local (0.136) y con la que resuelve el CI.
"""
from __future__ import annotations

from typing import Iterator


def rutas_de(app) -> list:
    """Todas las rutas reales de la app, con el path ya prefijado.

    Devuelve objetos con forma de ruta, no paths: los tests de RBAC necesitan
    mirarles `dependant`/`dependencies`. En 0.141 lo que sale es un
    `_EffectiveRouteContext`, que **no** es un `APIRoute` pero proxea todo lo
    que hace falta (`path` ya prefijado, `methods`, `dependant`) y guarda el
    original en `.original_route`. Por eso los tests filtran por `methods` y no
    con `isinstance(..., APIRoute)`, que ahora daría vacío.
    """
    return list(_iter_rutas(app))


def paths_de(app) -> set[str]:
    """Solo los paths, para los tests que chequean qué está montado."""
    return {r.path for r in _iter_rutas(app)}


def _iter_rutas(app) -> Iterator:
    for r in app.routes:
        if getattr(r, "path", None) is not None:
            yield r
            continue
        # FastAPI >= 0.141: el wrapper resuelve las rutas (ya con el prefijo
        # compuesto, incluso anidadas) en `effective_route_contexts`.
        contextos = getattr(r, "effective_route_contexts", None)
        if contextos is None:
            continue
        if callable(contextos):
            contextos = contextos()
        for ctx in contextos:
            ruta = getattr(ctx, "route", ctx)
            if getattr(ruta, "path", None) is not None:
                yield ruta
