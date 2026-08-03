"""Monitoreo de frescura de fuentes (`check_sources`, beat cada 6 h).

Detecta el caso que el status por-task no ve: la task corre "ok" pero el
dataset upstream dejó de avanzar (p.ej. InfoLEG 12 días atrasado sin que nadie
se entere). Evalúa cada fuente del registry (`vigia_shared.sources.SOURCES`)
contra su SLO y, si hay incidentes, marca `source_catalog.last_status='stale'`
y avisa por email (OPS_ALERT_EMAIL) + Sentry.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from vigia_shared.db import session_scope
from vigia_shared.sources import SOURCES
from vigia_workers.celery_app import celery_app
from vigia_workers.notifications import send_email
from vigia_workers.persistence import run_async

OPS_ALERT_EMAIL = os.environ.get("OPS_ALERT_EMAIL", "")


def _check_one(src_def: dict, row: Any | None, now: datetime, today: date) -> list[str]:
    """Evalúa una fuente del registry contra su fila agregada. Devuelve incidentes."""
    issues: list[str] = []
    if row is None:
        issues.append("nunca corrió (sin fila en source_catalog)")
        return issues

    if row.last_status == "error":
        # El fallback importa: si `last_error` viene vacío el mail decía
        # "última corrida en error:" y cortaba ahí, que es peor que no avisar —
        # sabés que algo falló y no tenés ni por dónde empezar. Pasó con
        # senado_proyectos el 2026-08-03.
        detalle = (row.last_error or "").strip()
        issues.append(
            f"última corrida en error: {detalle[:200]}"
            if detalle
            else "última corrida en error, pero la task no dejó mensaje "
                 "(revisar `docker logs vigia-worker-1`)"
        )

    cadence = src_def.get("cadence_hours")
    if cadence and row.last_run_at is not None:
        last_run = row.last_run_at
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=timezone.utc)
        if now - last_run > timedelta(hours=2 * cadence):
            issues.append(
                f"beat caído o task colgada: última corrida hace "
                f"{(now - last_run).days}d (cadencia {cadence}h)"
            )

    slo = src_def.get("freshness_slo_days")
    if slo and row.max_fecha is not None:
        age = (today - row.max_fecha).days
        if age > slo:
            issues.append(
                f"datos estancados: norma más reciente de hace {age}d (SLO {slo}d)"
            )
    return issues


async def _check_sources() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    today = now.date()

    async with session_scope() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT sc.code, sc.last_run_at, sc.last_status, sc.last_error,
                           MAX(n.fecha_publicacion) AS max_fecha,
                           COUNT(*) FILTER (
                               WHERE n.ingested_at > now() - interval '7 days'
                           ) AS inserted_7d
                    FROM source_catalog sc
                    LEFT JOIN norma n ON n.source_id = sc.id
                    GROUP BY sc.id
                    """
                )
            )
        ).all()
        by_code = {r.code: r for r in rows}

        report: dict[str, Any] = {}
        incidents: list[str] = []
        for code, src_def in SOURCES.items():
            row = by_code.get(code)
            issues = _check_one(src_def, row, now, today)
            report[code] = {
                "max_fecha": row.max_fecha.isoformat() if row is not None and row.max_fecha else None,
                "inserted_7d": int(row.inserted_7d) if row is not None else 0,
                "stale": bool(issues),
                "issues": issues,
            }
            if not issues:
                continue
            incidents.append(f"{code}: " + "; ".join(issues))
            # No pisar "error" (es información más específica que "stale").
            if row is not None and row.last_status != "error":
                await session.execute(
                    text(
                        "UPDATE source_catalog SET last_status = 'stale', last_error = :why "
                        "WHERE code = :code"
                    ),
                    {"code": code, "why": "; ".join(issues)[:1000]},
                )

    if incidents:
        body = "<br>".join(incidents)
        print(f"[freshness] incidentes: {incidents}")
        if OPS_ALERT_EMAIL:
            send_email(
                to=OPS_ALERT_EMAIL,
                subject=f"Vigía — {len(incidents)} fuente(s) con problemas de frescura",
                html=f"<div style='font-family:monospace'>{body}</div>",
            )
        try:  # Sentry es opcional (no-op sin SENTRY_DSN).
            import sentry_sdk

            sentry_sdk.capture_message(
                f"vigia sources stale: {'; '.join(incidents)}", level="warning"
            )
        except Exception:
            pass

    return {"checked": len(SOURCES), "incidents": len(incidents), "sources": report}


@celery_app.task(name="vigia_workers.freshness.check_sources")
def check_sources() -> dict[str, Any]:
    return run_async(_check_sources())
