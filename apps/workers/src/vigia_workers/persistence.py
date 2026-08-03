"""Helpers para upsert idempotente de normas y tracking de fuentes."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from vigia_shared.db import session_scope
from vigia_shared.models import DnuTracking, Norma, SourceCatalog


async def ensure_source(code: str) -> None:
    """Garantiza la fila de source_catalog para fuentes que no upsertean normas
    (p.ej. tracking bicameral): sin esto, mark_source_run sería un no-op."""
    from vigia_shared.sources import catalog_fields

    async with session_scope() as session:
        await _upsert_source(session, **catalog_fields(code))


async def mark_source_run(
    source_code: str, *, status: str = "ok", error: str | None = None
) -> None:
    """Actualiza SourceCatalog.last_run_at / last_status al final de cada task."""
    async with session_scope() as session:
        await session.execute(
            update(SourceCatalog)
            .where(SourceCatalog.code == source_code)
            .values(
                last_run_at=datetime.now(timezone.utc),
                last_status=status,
                last_error=error,
            )
        )


async def _upsert_source(
    session: AsyncSession,
    *,
    code: str,
    name: str,
    kind: str,
    base_url: str | None = None,
) -> int:
    res = await session.execute(select(SourceCatalog).where(SourceCatalog.code == code))
    row = res.scalar_one_or_none()
    if row is not None:
        return row.id
    new = SourceCatalog(code=code, name=name, kind=kind, base_url=base_url)
    session.add(new)
    await session.flush()
    return new.id


# Columnas de `norma` que el upsert sobreescribe cuando ya existe (no tocamos
# las identitarias ni search_vector, que es generada).
# `resumen_ia` se trata aparte (COALESCE): es caro de generar y muchas tasks
# re-ingestan sin recalcularlo (p.ej. InfoLEG full), así que no debe pisarse
# con NULL — solo se actualiza cuando el INSERT trae uno nuevo.
_NORMA_UPDATE_COLS = (
    "tipo", "numero", "titulo", "resumen", "resumen_ia", "fecha_publicacion",
    "jurisdiccion", "sector", "emisor", "organismo", "estado", "impacto", "bora_seccion",
    "entidades", "tags", "url", "raw",
)


async def upsert_normas(source: dict, normas: list[dict]) -> dict[str, int]:
    """Upsert idempotente por (source_id, external_id).

    `normas` es una lista de dicts con las columnas de `Norma` (sin source_id,
    que se inyecta acá). Devuelve `{"rows", "inserted", "updated"}` — el split
    insert/update (vía `xmax = 0`) es la señal de "fuente viva": una fuente
    diaria con 0 inserted por varios días está muerta aunque la task corra ok.
    Para los DNU nuevos se garantiza una fila en `dnu_tracking` (pendiente).
    """
    if not normas:
        return {"rows": 0, "inserted": 0, "updated": 0}
    # Dedup por external_id dentro del batch (última gana): Postgres rechaza un
    # ON CONFLICT DO UPDATE que afecte la misma fila dos veces en un comando.
    deduped: dict[str, dict] = {}
    for n in normas:
        deduped[n["external_id"]] = n
    normas = list(deduped.values())

    async with session_scope() as session:
        source_id = await _upsert_source(session, **source)

        values = [{**n, "source_id": source_id} for n in normas]
        stmt = insert(Norma).values(values)
        set_ = {col: getattr(stmt.excluded, col) for col in _NORMA_UPDATE_COLS}
        # Conservar el resumen IA existente cuando esta corrida no trae uno
        # (re-ingestas idempotentes, o fallo puntual del LLM en el lookback).
        set_["resumen_ia"] = func.coalesce(stmt.excluded.resumen_ia, Norma.resumen_ia)
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_id", "external_id"],
            set_=set_,
        ).returning(Norma.id, Norma.tipo, literal_column("(xmax = 0)").label("inserted"))
        res = await session.execute(stmt)
        rows = res.fetchall()

        # Garantizar tracking de DNU.
        dnu_ids = [r.id for r in rows if r.tipo == "DNU"]
        if dnu_ids:
            existing = await session.execute(
                select(DnuTracking.norma_id).where(DnuTracking.norma_id.in_(dnu_ids))
            )
            tracked = {row[0] for row in existing.all()}
            nuevos = [
                DnuTracking(norma_id=nid, estado_bicameral="pendiente")
                for nid in dnu_ids
                if nid not in tracked
            ]
            session.add_all(nuevos)

        inserted = sum(1 for r in rows if r.inserted)
        return {"rows": len(values), "inserted": inserted, "updated": len(values) - inserted}


def run_async(coro):
    """Corre una corutina async dentro de una task Celery sync."""
    return asyncio.run(coro)


async def with_status(source_codes: list[str], coro_factory):
    """Corre una coro y registra ok/error contra cada source_code."""
    try:
        result = await coro_factory()
    except Exception as exc:
        # El tipo va SIEMPRE, no solo cuando `str(exc)` está vacío. Las excepciones
        # de red —justo las más frecuentes acá— suelen tener str() vacío
        # (httpx.ConnectError(), ReadTimeout(), TimeoutError()), y entonces el mail
        # de frescura decía "última corrida en error:" y cortaba: sabías que algo
        # falló pero no qué. Con el tipo, un timeout se distingue de un 500 o de un
        # parseo roto sin entrar al servidor.
        detalle = str(exc).strip()
        mensaje = f"{type(exc).__name__}: {detalle}" if detalle else type(exc).__name__
        for code in source_codes:
            try:
                await mark_source_run(code, status="error", error=mensaje[:1000])
            except Exception:
                pass
        raise
    for code in source_codes:
        try:
            await mark_source_run(code, status="ok", error=None)
        except Exception:
            pass
    return result
