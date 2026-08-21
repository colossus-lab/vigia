"""Tareas de mantenimiento / retención de datos.

`purge_audit_log` borra los registros de `audit_log` (que incluyen IP y
user-agent) más viejos que `VIGIA_AUDIT_RETENTION_DAYS`. Aplica el principio de
limitación temporal de la Ley 25.326 (art. 4): no conservar datos personales por
más tiempo del necesario para la finalidad que los justificó.

`purge_creditos` borra los contadores de períodos viejos. La tabla crece una
fila por workspace y por período y nadie la limpia sola: en el sistema hermano
de Políticas Públicas el TTL se escribe en cada item pero nunca se activó, así
que los contadores se acumulan desde el día uno. Acá la purga es explícita.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from vigia_shared.creditos_db import purgar
from vigia_shared.db import session_scope
from vigia_workers.celery_app import celery_app
from vigia_workers.persistence import run_async

DEFAULT_RETENTION_DAYS = 365


def _retention_days() -> int:
    try:
        return max(1, int(os.environ.get("VIGIA_AUDIT_RETENTION_DAYS", str(DEFAULT_RETENTION_DAYS))))
    except (TypeError, ValueError):
        return DEFAULT_RETENTION_DAYS


async def _purge(days: int) -> dict[str, Any]:
    async with session_scope() as session:
        result = await session.execute(
            text("DELETE FROM audit_log WHERE created_at < now() - make_interval(days => :days)"),
            {"days": days},
        )
    return {"deleted": result.rowcount, "retention_days": days}


@celery_app.task(name="vigia_workers.maintenance.purge_audit_log")
def purge_audit_log() -> dict[str, Any]:
    return run_async(_purge(_retention_days()))


#: Cuántos períodos hacia atrás se conservan. 13 cubre un año de meses más el
#: que está en curso; el nivel `base` gasta dos por mes, así que le alcanza para
#: medio año. Es historial de cortesía: el saldo vivo es el del período actual.
PERIODOS_A_CONSERVAR = 13


def _periodos_vivos(hoy: date | None = None) -> list[str]:
    """Los períodos que NO se purgan, en las dos variantes (mensual y quincenal).

    Se enumeran en vez de comparar strings con `<`: el orden lexicográfico
    funcionaría para "2026-08" pero mete la quincena en el medio ("2026-08" <
    "2026-08q1" < "2026-09"), y un corte por prefijo se llevaría puesta la
    segunda quincena del mes más viejo que sí queremos conservar.
    """
    hoy = hoy or datetime.now(timezone.utc).date()
    vivos: list[str] = []
    cursor = hoy.replace(day=1)
    for _ in range(PERIODOS_A_CONSERVAR):
        mes = cursor.strftime("%Y-%m")
        vivos += [mes, f"{mes}q1", f"{mes}q2"]
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    return vivos


async def _purge_creditos() -> dict[str, Any]:
    async with session_scope() as session:
        borradas = await purgar(session, _periodos_vivos())
    return {"deleted": borradas, "periodos_conservados": PERIODOS_A_CONSERVAR}


@celery_app.task(name="vigia_workers.maintenance.purge_creditos")
def purge_creditos() -> dict[str, Any]:
    return run_async(_purge_creditos())
