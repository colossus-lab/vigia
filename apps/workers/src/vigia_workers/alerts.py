"""Matching de normas contra alertas + envío de notificaciones.

`match_alertas` corre tras cada ingesta (y por beat). Para cada alerta activa
busca normas que matcheen su keyword (FTS español) y sector opcional, que no
estén ya registradas en `alerta_match`, las inserta, y agrupa los matches
nuevos por (usuario, workspace) para mandar un digest.

Es el único lugar del sistema que cobra créditos: el digest es la única acción
medida (ver `vigia_shared.creditos`). Sin cupo no se manda el mail, pero el
match queda registrado igual — se pierde el aviso, nunca el dato.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import text

from vigia_shared import creditos as cred
from vigia_shared import creditos_db as cdb
from vigia_shared.db import session_scope
from vigia_workers.celery_app import celery_app
from vigia_workers.notifications import render_digest, render_sin_creditos, send_email
from vigia_workers.persistence import run_async


async def _match_all(notify: bool = True) -> dict[str, Any]:
    """Matchea normas contra alertas activas.

    `notify=False` (backfills): registra los matches con notified=true SIN
    mandar digests, sin cobrar créditos y sin avisar que se agotaron — sin esto,
    el primer backfill de una fuente nueva spamea a los usuarios con miles de
    normas viejas. Runbook de fuente nueva: backfill → `_match_all(notify=False)`
    → recién ahí habilitar el beat.
    """
    new_total = 0
    # (email, workspace_id) -> (workspace_name, plan, aporte, [items])
    #
    # La clave lleva el workspace y no solo el email a propósito. Antes era solo
    # el email y el nombre del workspace se pisaba con el del último alerta
    # procesado, así que quien está en dos workspaces recibía un mail rotulado
    # con el equivocado. Además, sin el workspace en la clave no se sabe a quién
    # cobrarle el digest.
    digests: dict[tuple[str, int], tuple[str, str, dict | None, list[dict]]] = {}
    # Ids insertados en ESTA corrida, para no marcar como notificados los de otra.
    insertados: list[int] = []

    async with session_scope() as session:
        alertas = (
            await session.execute(
                text(
                    """
                    SELECT a.id, a.keywords, a.sectores, a.anchor_at, a.workspace_id,
                           w.name AS ws_name, w.plan AS ws_plan, w.aporte AS ws_aporte,
                           u.email AS user_email
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

            # El NOT EXISTS filtra el caso común, pero es un chequeá-y-después-
            # insertá: entre el SELECT y el INSERT otra corrida puede meter la
            # misma fila y esta revienta con UniqueViolation, abortando el
            # matcheo de esa hora (pasó 4 veces en 7 días). El ON CONFLICT cierra
            # la ventana. `RETURNING` sigue devolviendo SOLO las filas realmente
            # insertadas, así que las que pierden la carrera no re-notifican.
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
                        ON CONFLICT ON CONSTRAINT uq_match_alerta_norma DO NOTHING
                        RETURNING id, norma_id
                        """
                    ),
                    params,
                )
            ).all()

            if not inserted:
                continue
            new_total += len(inserted)
            insertados.extend(int(r[0]) for r in inserted)
            await session.execute(
                text("UPDATE alerta SET last_match_at = now() WHERE id = :aid"), {"aid": a.id}
            )

            if a.user_email and notify:
                norma_ids = [r[1] for r in inserted]
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
                clave = (a.user_email, a.workspace_id)
                _, _, _, items = digests.get(clave, ("", "", None, []))
                digests[clave] = (
                    a.ws_name,
                    a.ws_plan,
                    a.ws_aporte,
                    items + [
                        {"id": n.id, "keyword": kw_label, "tipo": n.tipo,
                         "numero": n.numero, "titulo": n.titulo}
                        for n in normas
                    ],
                )

        # Marcar como notificados SOLO los matches de esta corrida. Antes era un
        # UPDATE global `WHERE notified = false`, que también se llevaba puestos
        # los que otra corrida acababa de insertar y todavía no había mandado.
        if insertados:
            await session.execute(
                text("UPDATE alerta_match SET notified = true WHERE id = ANY(:ids)"),
                {"ids": insertados},
            )

        # Saldo de cada workspace que recibiría un digest, en una sola query.
        claves_cred = {
            (ws_id, cred.periodo_de(plan, aporte))
            for (_, ws_id), (_, plan, aporte, _) in digests.items()
        }
        usados = await cdb.leer_varios(session, sorted(claves_cred))

    # Decidir a quién se le manda, antes de mandar nada. `gastado` acumula lo que
    # se cobra en esta misma corrida: sin eso, un workspace con varios miembros
    # leería el mismo saldo viejo para todos y se pasaría del cupo por tantos
    # digests como gente tenga.
    a_enviar: list[tuple[str, str, list[dict], tuple[int, str]]] = []   # email, ws_name, items, clave
    a_avisar: list[tuple[int, str, str, str, dict]] = []      # ws_id, periodo, email, ws_name, estado
    gastado: dict[tuple[int, str], int] = defaultdict(int)
    omitidos = 0

    for (email, ws_id), (ws_name, plan, aporte, items) in digests.items():
        if not items:
            continue
        periodo = cred.periodo_de(plan, aporte)
        clave = (ws_id, periodo)
        estado = cred.estado(usados.get(clave, 0) + gastado[clave], plan, aporte)

        if estado["agotados"]:
            # Sin cupo no se manda el digest, pero los matches ya quedaron
            # registrados y se ven en la app: se pierde el aviso, no el dato.
            omitidos += 1
            a_avisar.append((ws_id, periodo, email, ws_name, estado))
            continue

        a_enviar.append((email, ws_name, items, clave))
        gastado[clave] += cred.micros_de("digest")

    # Reservar los avisos ANTES de mandarlos: `tomar_aviso_agotado` es un UPDATE
    # condicional que gana la carrera en la base. El matcher corre cada hora, y
    # sin ese candado le llegaría un mail por hora a alguien para avisarle que
    # dejamos de mandarle mails.
    avisos_ganados: list[tuple[str, str, dict]] = []
    if a_avisar:
        async with session_scope() as session:
            vistos: set[tuple[int, str]] = set()
            for ws_id, periodo, email, ws_name, estado in a_avisar:
                if (ws_id, periodo) in vistos:
                    continue
                vistos.add((ws_id, periodo))
                if await cdb.tomar_aviso_agotado(session, ws_id, periodo):
                    avisos_ganados.append((email, ws_name, estado))

    # Enviar (fuera de toda transacción: una demora de Resend no puede tener
    # abierta la transacción que escribe los matches).
    sent = 0
    cobros: dict[tuple[int, str], int] = defaultdict(int)
    for email, ws_name, items, clave in a_enviar:
        subject = (
            "Vigía — 1 nueva norma para tus alertas"
            if len(items) == 1
            else f"Vigía — {len(items)} nuevas normas para tus alertas"
        )
        resultado = send_email(to=email, subject=subject, html=render_digest(ws_name, items))
        if resultado.get("error"):
            continue
        sent += 1
        # Solo se cobra lo que Resend aceptó. Sin RESEND_API_KEY `send_email`
        # devuelve {"skipped": True} y no sale nada: en dev el contador no se
        # mueve, que es lo honesto.
        if resultado.get("sent"):
            cobros[clave] += cred.micros_de("digest")

    for email, ws_name, estado in avisos_ganados:
        send_email(
            to=email,
            subject="Vigía — se te acabaron los créditos de este mes",
            html=render_sin_creditos(ws_name, estado["renueva"], estado["contacto"]),
        )

    # Cobrar al final, en una sola sesión. El aviso NO se cobra: cobrarlo sería
    # un callejón sin salida.
    if cobros:
        async with session_scope() as session:
            for (ws_id, periodo), micros in cobros.items():
                await cdb.sumar(session, ws_id, periodo, micros)

    return {
        "new_matches": new_total,
        "emails": sent,
        "omitidos": omitidos,
        "avisados": len(avisos_ganados),
        "notify": notify,
    }


@celery_app.task(name="vigia_workers.alerts.match_alertas")
def match_alertas(notify: bool = True) -> dict[str, Any]:
    return run_async(_match_all(notify=notify))
