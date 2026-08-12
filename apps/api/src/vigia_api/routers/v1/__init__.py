"""API pública versionada.

Todo lo que cuelga de `/v1` es **contrato con terceros**: se puede agregar, no
sacar ni cambiar de forma. Lo que sirve al web de Vigía sigue viviendo en los
routers sin prefijo (`/normas`, `/search`, …), que se mueven cuando el web los
necesita. Son dos superficies distintas aunque lean la misma tabla, y el precio
de mezclarlas es que un ajuste de UI rompa la integración de otro.

Cuando `/v2` haga falta, `/v1` sigue montado en paralelo hasta que se anuncie su
baja.

Autenticación: **todo `/v1` exige una API key** (`Authorization: Bearer vg_live_…`).
No cierra nada que estuviera abierto — `/v1` nació con la key — y es lo que
permite saber quién consume qué y cortar un abuso puntual sin tocar a los demás.
Los endpoints que usa el web (`/normas`, `/search`, …) siguen públicos y sin
credencial, como siempre.

La cuota va en el mismo lugar, como dependency del router entero: si se colgara
de cada endpoint, sumar uno nuevo significaría acordarse de limitarlo.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from vigia_api.core.ratelimit import limitar_por_apikey
from vigia_api.routers.v1 import normas

router = APIRouter(dependencies=[Depends(limitar_por_apikey("v1"))])
router.include_router(normas.router)

__all__ = ["router"]
