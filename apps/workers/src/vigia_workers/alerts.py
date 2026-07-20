"""Matching de normas contra alertas + envío de notificaciones.

`match_alertas` corre tras cada ingesta (y por beat). Para cada alerta activa
busca normas que matcheen su keyword (FTS español) y sector opcional, que no
estén ya registradas en `alerta_match`, las inserta, y agrupa los matches
nuevos por email de usuario para mandar un digest.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import text

from vigia_shared.db import session_scope
from vigia_workers.celery_app import celery_app
from vigia_workers.notifications import render_digest, send_email
from vigia_workers.persistence import run_async


async def _match_all(notify: bool = True) -> dict[str, Any]:
    """Matchea normas contra alertas activas.

    `notify=False` (backfills): registra los matches con notified=true SIN
    mandar digests — sin esto, el primer backfill de una fuente nueva spamea
    a los usuarios con miles de normas viejas. Runbook de fuente nueva:
    backfill → `_match_all(notify=False)` → recién ahí habilitar el beat.
    """
    new_total = 0
    # email -> (workspace_name, [items])
    digests: dict[str, tuple[str, list[dict]]] = defaultdict(lambda: ("", []))

    async with session_scope() as session:
        alertas = (
            await session.execute(
                text(
                    """
                    SELECT a.id, a.keywords, a.sectores, a.anchor_at, a.workspace_id,
                           w.name AS ws_name, u.email AS user_email
                    FROM alerta a
                    JOIN workspace w ON w.id = a.workspace_id
                    LEFT JOIN app_user u ON u.id = a.user_id
                    WHERE a.activa = true
                    """
                )
            )
        ).all()

        for a in alertas:
            # OR entre keywords: una tsquery por keyword unidas con '||'.
            params: dict[str, Any] = {"aid": a.id, "anchor": a.anchor_at}
            ts_parts = []
            for i, kw in enumerate(a.keywords or []):
                ts_parts.append(f"plainto_tsquery('spanish', :kw{i})")
                params[f"kw{i}"] = kw

            # OR entre sectores (lista vacía = cualquier sector).
            sector_clause = ""
            if a.sectores:
                sector_clause = "AND n.sector = ANY(:sectores)"
                params["sectores"] = a.sectores

            # Una alerta necesita al menos un criterio. Con keywords → filtro FTS;
            # sin keywords pero con sectores → alerta por-sector (matchea todas las
            # normas del sector). Sin ninguno de los dos, nada que matchear.
            if not ts_parts and not sector_clause:
                continue
            ts_clause = f"AND n.search_vector @@ ({' || '.join(ts_parts)})" if ts_parts else ""

            inserted = (
                await session.execute(
                    text(
                        f"""
                        INSERT INTO alerta_match (alerta_id, norma_id, notified)
                        SELECT :aid, n.id, false
                        FROM norma n
                        WHERE n.ingested_at >= :anchor
                          {ts_clause}
                          {sector_clause}
                          AND NOT EXISTS (
                              SELECT 1 FROM alerta_match m
                              WHERE m.alerta_id = :aid AND m.norma_id = n.id
                          )
                        RETURNING norma_id
                        """
                    ),
                    params,
                )
            ).all()

            if not inserted:
                continue
            new_total += len(inserted)
            await session.execute(
                text("UPDATE alerta SET last_match_at = now() WHERE id = :aid"), {"aid": a.id}
            )

            if a.user_email and notify:
                norma_ids = [r[0] for r in inserted]
                normas = (
                    await session.execute(
                        text(
                            "SELECT id, tipo, numero, titulo FROM norma WHERE id = ANY(:ids) LIMIT 20"
                        ),
                        {"ids": norma_ids},
                    )
                ).all()
                kw_label = ", ".join(a.keywords or []) or (
                    "sectores: " + ", ".join(a.sectores or [])
                )
                _, items = digests[a.user_email]
                digests[a.user_email] = (
                    a.ws_name,
                    items + [
                        {"id": n.id, "keyword": kw_label, "tipo": n.tipo,
                         "numero": n.numero, "titulo": n.titulo}
                        for n in normas
                    ],
                )

        # Marcar como notificados los matches recién insertados.
        if new_total:
            await session.execute(text("UPDATE alerta_match SET notified = true WHERE notified = false"))

    # Enviar digests (fuera de la transacción).
    sent = 0
    for email, (ws_name, items) in digests.items():
        if not items:
            continue
        subject = (
            "Vigía — 1 nueva norma para tus alertas"
            if len(items) == 1
            else f"Vigía — {len(items)} nuevas normas para tus alertas"
        )
        send_email(
            to=email,
            subject=subject,
            html=render_digest(ws_name, items),
        )
        sent += 1

    return {"new_matches": new_total, "emails": sent, "notify": notify}


@celery_app.task(name="vigia_workers.alerts.match_alertas")
def match_alertas(notify: bool = True) -> dict[str, Any]:
    return run_async(_match_all(notify=notify))
