"""API pública versionada.

Todo lo que cuelga de `/v1` es **contrato con terceros**: se puede agregar, no
sacar ni cambiar de forma. Lo que sirve al web de Vigía sigue viviendo en los
routers sin prefijo (`/normas`, `/search`, …), que se mueven cuando el web los
necesita. Son dos superficies distintas aunque lean la misma tabla, y el precio
de mezclarlas es que un ajuste de UI rompa la integración de otro.

Cuando `/v2` haga falta, `/v1` sigue montado en paralelo hasta que se anuncie su
baja.
"""
from __future__ import annotations

from fastapi import APIRouter

from vigia_api.routers.v1 import normas

router = APIRouter()
router.include_router(normas.router)

__all__ = ["router"]
