from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import text

from vigia_api.core.db import get_sessionmaker
from vigia_shared.sources import SOURCES

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/detailed")
async def health_detailed() -> dict:
    """Liveness + freshness por fuente + conteo de normas."""
    Session = get_sessionmaker()
    async with Session() as session:
        total = (await session.execute(text("SELECT COUNT(*) FROM norma"))).scalar_one()
        sources = (
            await session.execute(
                text(
                    "SELECT code, name, last_run_at, last_status "
                    "FROM source_catalog ORDER BY code"
                )
            )
        ).all()
    return {
        "status": "ok",
        "normas": int(total or 0),
        "sources": [
            {
                "code": s[0],
                "name": s[1],
                "last_run_at": s[2].isoformat() if s[2] else None,
                "last_status": s[3],
            }
            for s in sources
        ],
    }


def _warnings(row) -> list[str]:
    """Avisos que la task dejó sin que la fuente esté rota ni estancada.

    Van aparte de `stale_reasons` a propósito. Los guards de ingesta escriben
    `last_status='warn'` para cosas que son ciertas pero permanentes —el listado
    del BORA truncado en 100 pasa TODOS los días en la 2ª sección— y meterlas en
    `stale` dejaría a la fuente en rojo fijo, que es la forma más rápida de que
    nadie vuelva a mirar el endpoint. Hasta ahora estos motivos no se veían en
    ningún lado: se escribían en `last_error` y `_stale_reasons` los filtraba.
    """
    if row.last_status == "warn" and row.last_error:
        return [str(row.last_error)[:300]]
    return []


def _stale_reasons(src_def: dict | None, row, now: datetime, today: date) -> list[str]:
    """Misma semántica que vigia_workers.freshness, para consulta sin ssh."""
    reasons: list[str] = []
    if row.last_status in ("error", "stale") and row.last_error:
        reasons.append(str(row.last_error)[:200])
    if src_def is None:
        return reasons  # fuente fuera del registry: sin SLOs que evaluar
    cadence = src_def.get("cadence_hours")
    if cadence and row.last_run_at is not None:
        last_run = row.last_run_at
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=timezone.utc)
        if now - last_run > timedelta(hours=2 * cadence):
            reasons.append(f"última corrida hace {(now - last_run).days}d (cadencia {cadence}h)")
    slo = src_def.get("freshness_slo_days")
    if slo and row.max_fecha is not None and (today - row.max_fecha).days > slo:
        reasons.append(f"norma más reciente de hace {(today - row.max_fecha).days}d (SLO {slo}d)")
    return reasons


@router.get("/health/sources")
async def health_sources() -> dict:
    """Estado operativo por fuente: última corrida, frescura de datos y flag stale.

    Es el target de los smoke tests post-deploy: una fuente recién agregada
    debe aparecer acá con last_status='ok' y max_fecha_publicacion razonable.
    """
    now = datetime.now(timezone.utc)
    today = now.date()
    Session = get_sessionmaker()
    async with Session() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT sc.code, sc.name, sc.kind, sc.last_run_at, sc.last_status,
                           sc.last_error,
                           MAX(n.fecha_publicacion) AS max_fecha,
                           COUNT(n.id) AS normas,
                           COUNT(*) FILTER (
                               WHERE n.ingested_at > now() - interval '7 days'
                           ) AS inserted_7d
                    FROM source_catalog sc
                    LEFT JOIN norma n ON n.source_id = sc.id
                    GROUP BY sc.id
                    ORDER BY sc.code
                    """
                )
            )
        ).all()

    seen = set()
    out = []
    for r in rows:
        seen.add(r.code)
        reasons = _stale_reasons(SOURCES.get(r.code), r, now, today)
        warns = _warnings(r)
        out.append(
            {
                "code": r.code,
                "name": r.name,
                "kind": r.kind,
                "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
                "last_status": r.last_status,
                "normas": int(r.normas or 0),
                "inserted_7d": int(r.inserted_7d or 0),
                "max_fecha_publicacion": r.max_fecha.isoformat() if r.max_fecha else None,
                "stale": bool(reasons),
                "stale_reasons": reasons or None,
                "warnings": warns or None,
            }
        )
    # Fuentes esperadas que todavía no corrieron nunca.
    for code in SOURCES:
        if code not in seen:
            out.append(
                {
                    "code": code,
                    "name": SOURCES[code]["name"],
                    "kind": SOURCES[code]["kind"],
                    "last_run_at": None,
                    "last_status": None,
                    "normas": 0,
                    "inserted_7d": 0,
                    "max_fecha_publicacion": None,
                    "stale": True,
                    "stale_reasons": ["nunca corrió"],
                    "warnings": None,
                }
            )
    return {"status": "ok", "sources": out}
