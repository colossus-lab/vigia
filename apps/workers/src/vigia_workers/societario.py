"""Radar societario: BORA 2ª sección → tabla `aviso_societario`.

NO escribe en `norma` (decisión de producto): ~200-400 avisos/día de
constituciones, asambleas y edictos dominarían el feed, las stats y las
alertas. Tabla propia con su tsvector (razón social peso A) y router
`/avisos`. Las alertas sobre avisos son una fase posterior.

El texto del detalle se fetchea solo para avisos NUEVOS (los ya ingestados
no se re-fetchean: con lookback 3 serían ~1000 requests diarios al pedo).
"""
from __future__ import annotations

import asyncio
import dataclasses
import os
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert

from vigia_connectors import LISTADO_TOPE, BoraClient, listado_truncado
from vigia_shared.db import session_scope
from vigia_shared.models import AvisoSocietario
from vigia_workers.celery_app import celery_app
from vigia_workers.persistence import ensure_source, mark_source_run, run_async, with_status

_BATCH = 500


async def _existing_ids(fechas: list[date]) -> set[str]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                text("SELECT aviso_id FROM aviso_societario WHERE fecha = ANY(:fechas)"),
                {"fechas": fechas},
            )
        ).scalars().all()
    return set(rows)


async def _upsert(avisos: list[dict[str, Any]]) -> int:
    if not avisos:
        return 0
    inserted = 0
    async with session_scope() as session:
        for i in range(0, len(avisos), _BATCH):
            chunk = avisos[i : i + _BATCH]
            stmt = insert(AvisoSocietario).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["aviso_id"],
                set_={
                    "razon_social": stmt.excluded.razon_social,
                    "rubro": stmt.excluded.rubro,
                    "url": stmt.excluded.url,
                    "raw": stmt.excluded.raw,
                    # texto: no pisar con NULL un texto ya fetcheado.
                    "texto": func.coalesce(stmt.excluded.texto, AvisoSocietario.__table__.c.texto),
                },
            )
            res = await session.execute(stmt)
            inserted += res.rowcount or 0
    return inserted


@celery_app.task(name="vigia_workers.societario.ingest_bora_segunda")
def ingest_bora_segunda(dry_run: bool = False, lookback_days: int = 3) -> dict[str, Any]:
    dry = dry_run or os.environ.get("VIGIA_INGEST_DRY_RUN", "").strip().lower() in ("1", "true", "yes")
    hoy = date.today()
    fechas = [hoy - timedelta(days=d) for d in range(lookback_days)]

    async def _run() -> dict[str, Any]:
        total = 0
        con_texto = 0
        sample: list[dict[str, Any]] = []
        truncadas: list[str] = []
        existentes = set() if dry else await _existing_ids(fechas)
        async with BoraClient() as client:
            for fecha in fechas:
                avisos = await client.fetch_seccion("segunda", fecha)
                if listado_truncado(avisos):
                    truncadas.append(fecha.isoformat())
                if not avisos:
                    continue
                nuevos = [a for a in avisos if a.aviso_id not in existentes]
                textos: dict[str, str | None] = {}
                if not dry and nuevos:
                    fetched = await asyncio.gather(
                        *(client.fetch_detalle_texto(a) for a in nuevos),
                        return_exceptions=True,
                    )
                    textos = {
                        a.aviso_id: (t if not isinstance(t, Exception) else None)
                        for a, t in zip(nuevos, fetched)
                    }
                rows = [
                    {
                        "aviso_id": a.aviso_id,
                        "fecha": a.fecha,
                        "razon_social": (a.organismo or None),
                        "rubro": a.rubro,
                        "texto": (textos.get(a.aviso_id) or None),
                        "url": a.url,
                        "raw": {k: (v.isoformat() if isinstance(v, date) else v)
                                for k, v in dataclasses.asdict(a).items()},
                    }
                    for a in avisos
                ]
                con_texto += sum(1 for r in rows if r["texto"])
                total += len(rows)
                if dry:
                    sample.extend(
                        {"aviso_id": r["aviso_id"], "razon_social": r["razon_social"],
                         "rubro": r["rubro"], "fecha": r["fecha"].isoformat()}
                        for r in rows[: max(0, 5 - len(sample))]
                    )
                    continue
                await _upsert(rows)
        out: dict[str, Any] = {"rows": total, "con_texto": con_texto, "truncadas": truncadas}
        if dry:
            out["sample"] = sample
        return out

    if dry:
        result = run_async(_run())
        return {"source": "bora_segunda", "dry_run": True, **result}

    async def _wrapped() -> dict[str, Any]:
        await ensure_source("bora_segunda")
        counts = await with_status(["bora_segunda"], _run)
        return {"source": "bora_segunda", **counts}

    result = run_async(_wrapped())

    # Acá el truncamiento no es la excepción: la 2ª sección publica ~200-400
    # avisos por día y el listado corta en 100, así que esto va a quedar en warn
    # todos los días hábiles hasta que haya paginación. Es a propósito — la
    # fuente ESTÁ incompleta todos los días y hasta ahora reportaba "ok".
    # `warn` no dispara el mail de ops (freshness.py solo escala `error`) ni
    # marca la fuente como stale: queda como motivo visible en /health/sources.
    truncadas = result.get("truncadas") or []
    if truncadas:
        run_async(
            mark_source_run(
                "bora_segunda",
                status="warn",
                error=(
                    f"listado truncado en el tope de {LISTADO_TOPE} avisos: "
                    f"{len(truncadas)} de {len(fechas)} ediciones ({', '.join(truncadas)}) — "
                    "la 2ª sección publica bastante más que eso por día"
                ),
            )
        )
    return result
