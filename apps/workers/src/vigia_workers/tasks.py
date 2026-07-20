"""Tasks de ingesta de Celery.

Cada task es idempotente (upsert por (source_id, external_id)). Se pueden
invocar desde CLI:

    python -c "from vigia_workers.tasks import ingest_infoleg as t; print(t())"

…o agendar por celery-beat (ver celery_app.py).

Dry-run (no escribe en la DB; fetch + parse + conteos + sample de filas):

    python -c "from vigia_workers.tasks import ingest_infoleg as t; print(t(dry_run=True))"

…o exportando VIGIA_INGEST_DRY_RUN=1 (aplica a todas las tasks de ingesta).
"""
from __future__ import annotations

import dataclasses
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from vigia_connectors import (
    BoCabaClient, BoCabaNorma, BoPbaClient, BoPbaNorma, BoraAviso, BoraClient,
    HcdnClient, HcdnProyecto, InfoLegClient, InfoLegNorm, SenadoClient, SenadoProyecto,
)
from vigia_connectors.bora import looks_like_dnu
from vigia_connectors.emisores import detect_emisor
from vigia_shared.sources import catalog_fields
from vigia_workers.ai_resumen import aplicar_resumen_ia
from vigia_workers.celery_app import celery_app
from vigia_workers.persistence import mark_source_run, run_async, upsert_normas, with_status

INFOLEG_SOURCE = catalog_fields("infoleg")
HCDN_SOURCE = catalog_fields("hcdn_proyectos")
BORA_SOURCE = catalog_fields("bora_primera")

# Cuántos registros por batch al persistir el corpus completo.
# Tope: asyncpg admite máx 32767 parámetros bind por statement
# (~17 columnas por fila → 1000 filas ≈ 17k params, margen cómodo).
_FULL_BATCH = 1000

# Cuántas filas de muestra reporta un dry-run.
_DRY_SAMPLE = 5


def _is_dry_run(flag: bool) -> bool:
    return flag or os.environ.get("VIGIA_INGEST_DRY_RUN", "").strip().lower() in ("1", "true", "yes")


def _dry_sample_row(row: dict[str, Any]) -> dict[str, Any]:
    """Versión legible de una fila para el reporte de dry-run (sin raw)."""
    keep = ("external_id", "tipo", "numero", "titulo", "resumen", "fecha_publicacion", "organismo", "sector")
    out = {k: row.get(k) for k in keep}
    if isinstance(out.get("fecha_publicacion"), date):
        out["fecha_publicacion"] = out["fecha_publicacion"].isoformat()
    return out


def _empty_totals() -> dict[str, int]:
    return {"rows": 0, "inserted": 0, "updated": 0}


def _acc(totals: dict[str, int], part: dict[str, int]) -> None:
    for k in ("rows", "inserted", "updated"):
        totals[k] += part[k]


def _norma_to_row(n: InfoLegNorm) -> dict[str, Any]:
    """Mapea un InfoLegNorm al shape de la tabla `norma`."""
    titulo = n.titulo_resumido or n.titulo_sumario or f"{n.tipo_norma} {n.numero_norma or ''}".strip()
    resumen = n.texto_resumido or n.titulo_sumario
    fecha = n.fecha_boletin or n.fecha_sancion
    return {
        "external_id": n.id_norma,
        "tipo": n.tipo_slug(),
        "numero": n.numero_norma,
        "titulo": titulo,
        "resumen": resumen,
        "resumen_ia": None,
        "fecha_publicacion": fecha,
        "jurisdiccion": "Nacional",
        "sector": n.detect_sector(),
        "organismo": n.organismo_origen,
        "emisor": detect_emisor(n.organismo_origen),
        "estado": "Publicada" if n.fecha_boletin else None,
        "impacto": None,  # heurística de impacto -> fase posterior
        "bora_seccion": "Primera Sección" if n.numero_boletin else None,
        "entidades": None,  # NER -> Fase 5
        "tags": None,
        "url": n.texto_original_url,
        "raw": {k: (v.isoformat() if isinstance(v, date) else v)
                for k, v in dataclasses.asdict(n).items()},
    }


@celery_app.task(name="vigia_workers.tasks.ingest_infoleg")
def ingest_infoleg(dry_run: bool = False, notify: bool = True) -> dict[str, Any]:
    """Ingesta el muestreo de InfoLEG (~1000 normas). Rápido — bueno para dev."""
    dry = _is_dry_run(dry_run)

    async def _run() -> dict[str, Any]:
        async with InfoLegClient() as client:
            normas = await client.fetch_sample()
        rows = [_norma_to_row(n) for n in normas]
        if dry:
            return {"rows": len(rows), "sample": [_dry_sample_row(r) for r in rows[:_DRY_SAMPLE]]}
        return await upsert_normas(INFOLEG_SOURCE, rows)

    if dry:
        result = run_async(_run())
        return {"source": "infoleg", "mode": "sample", "dry_run": True, **result}

    async def _wrapped() -> dict[str, Any]:
        counts = await with_status([INFOLEG_SOURCE["code"]], _run)
        return {"source": "infoleg", "mode": "sample", **counts}

    result = run_async(_wrapped())
    # Tras ingestar, cruzar contra las alertas activas y notificar.
    from vigia_workers.alerts import _match_all
    result["matching"] = run_async(_match_all(notify=notify))
    return result


def _proyecto_to_row(p: HcdnProyecto) -> dict[str, Any]:
    """Mapea un HcdnProyecto al shape de la tabla `norma` (tipo PROYECTO)."""
    return {
        "external_id": p.proyecto_id,
        "tipo": "PROYECTO",
        "numero": p.expediente,
        "titulo": p.titulo,
        "resumen": None,
        "resumen_ia": None,
        "fecha_publicacion": p.fecha_publicacion,
        "jurisdiccion": "Nacional",
        "sector": p.detect_sector(),
        "organismo": p.organismo(),
        "emisor": detect_emisor(p.organismo()),
        "estado": "En trámite",
        "impacto": None,
        "bora_seccion": None,
        "entidades": [p.autor] if p.autor else None,
        "tags": [p.tipo_proyecto.lower()] if p.tipo_proyecto else None,
        "url": None,
        "raw": {k: (v.isoformat() if isinstance(v, date) else v)
                for k, v in dataclasses.asdict(p).items()},
    }


@celery_app.task(name="vigia_workers.tasks.ingest_hcdn_proyectos")
def ingest_hcdn_proyectos(dry_run: bool = False, notify: bool = True) -> dict[str, Any]:
    """Ingesta los proyectos parlamentarios de HCDN (CSV completo por streaming).

    El dataset se actualiza a diario en datos.hcdn.gob.ar; el upsert es
    idempotente por (source_id, external_id=PROYECTO_ID).
    """
    dry = _is_dry_run(dry_run)

    async def _run() -> dict[str, Any]:
        totals = _empty_totals()
        sample: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "proyectos.csv"
            async with HcdnClient() as client:
                await client.download_csv(dest)
            batch: list[dict[str, Any]] = []
            for p in HcdnClient.iter_csv(dest):
                row = _proyecto_to_row(p)
                if dry:
                    totals["rows"] += 1
                    if len(sample) < _DRY_SAMPLE:
                        sample.append(_dry_sample_row(row))
                    continue
                batch.append(row)
                if len(batch) >= _FULL_BATCH:
                    _acc(totals, await upsert_normas(HCDN_SOURCE, batch))
                    batch = []
            if batch:
                _acc(totals, await upsert_normas(HCDN_SOURCE, batch))
        if dry:
            return {"rows": totals["rows"], "sample": sample}
        return totals

    if dry:
        result = run_async(_run())
        return {"source": "hcdn_proyectos", "dry_run": True, **result}

    async def _wrapped() -> dict[str, Any]:
        counts = await with_status([HCDN_SOURCE["code"]], _run)
        return {"source": "hcdn_proyectos", **counts}

    return run_async(_wrapped())


def _senado_to_row(p: SenadoProyecto) -> dict[str, Any]:
    """Mapea un SenadoProyecto al shape de la tabla `norma` (tipo PROYECTO)."""
    return {
        "external_id": p.external_id,
        "tipo": "PROYECTO",
        "numero": f"{p.numero}/{p.anio}",
        "titulo": p.extracto,
        "resumen": None,
        "resumen_ia": None,
        "fecha_publicacion": p.fecha,
        "jurisdiccion": "Nacional",
        "sector": p.detect_sector(),
        "emisor": None,  # el Senado no es un organismo regulador emisor
        "organismo": "Honorable Senado de la Nación",
        "estado": "En trámite",
        "impacto": None,
        "bora_seccion": None,
        "entidades": p.autores or None,
        "tags": [p.tipo_proyecto] if p.tipo_proyecto else None,
        "url": p.url,
        "raw": {
            "numero": p.numero, "anio": p.anio, "tipo_codigo": p.tipo_codigo,
            "origen": p.origen, "autores": p.autores,
            "fecha": p.fecha.isoformat() if p.fecha else None,
        },
    }


@celery_app.task(name="vigia_workers.tasks.ingest_senado_proyectos")
def ingest_senado_proyectos(dry_run: bool = False, max_pages: int = 3, notify: bool = True) -> dict[str, Any]:
    """Ingesta proyectos recientes originados en el Senado (scrape del buscador HSN).

    Solo origen=S (los venidos de Diputados ya están en hcdn_proyectos). Upsert
    idempotente por external_id = '{numero}/{anio}-{origen}-{tipo}'.
    """
    dry = _is_dry_run(dry_run)
    SOURCE = catalog_fields("senado_proyectos")

    async def _run() -> dict[str, Any]:
        async with SenadoClient() as client:
            proyectos = await client.fetch_recientes(max_pages=max_pages)
        rows = [_senado_to_row(p) for p in proyectos]
        if dry:
            return {"rows": len(rows), "sample": [_dry_sample_row(r) for r in rows[:_DRY_SAMPLE]]}
        totals = _empty_totals()
        for i in range(0, len(rows), _FULL_BATCH):
            _acc(totals, await upsert_normas(SOURCE, rows[i : i + _FULL_BATCH]))
        return totals

    if dry:
        result = run_async(_run())
        return {"source": "senado_proyectos", "dry_run": True, **result}

    async def _wrapped() -> dict[str, Any]:
        counts = await with_status([SOURCE["code"]], _run)
        return {"source": "senado_proyectos", **counts}

    result = run_async(_wrapped())
    from vigia_workers.alerts import _match_all
    result["matching"] = run_async(_match_all(notify=notify))
    return result


# Código GDE/GEDO (Gestión Documental Electrónica): RESOL-2026-276-APN-INASE#MEC,
# DI-2026-12-APN-DNGRH#MS, DECTO-2026-443-APN-PTE, RESFC-2026-1-APN-MEC#MEC, …
# El BORA usa esto como "sumario" para muchísimas resoluciones/disposiciones —
# es el identificador del documento, no un resumen humano. Un sumario real es
# una oración con espacios, así que el anclaje ^…$ sin espacios no da falsos +.
_CODIGO_GDE_RE = re.compile(
    r"^[A-Z]{2,8}-\d{4}-\d+(?:-[A-Z0-9]+)+(?:#[A-Z0-9]+)?$", re.IGNORECASE
)


def _es_codigo_documento(s: str | None) -> bool:
    """True si el string es un código GDE y no un sumario en prosa."""
    return bool(s and _CODIGO_GDE_RE.match(s.strip()))


def _sumario_generico(a: BoraAviso) -> bool:
    """True si el listado no trae sumario útil (p.ej. rubro "Avisos Oficiales",
    donde el único item-detalle es el literal "Aviso Oficial")."""
    s = (a.sumario or "").strip().lower()
    return not s or s == (a.tipo_linea or "").strip().lower()


def _sumario_sin_valor(a: BoraAviso) -> bool:
    """El listado no aporta un sumario legible: vacío, == tipo+número, o un
    código GDE. En todos estos casos bajamos el detalle y armamos el resumen
    real desde el cuerpo del aviso."""
    return _sumario_generico(a) or _es_codigo_documento(a.sumario)


def _texto_excerpt(texto: str, max_len: int) -> str:
    import re as _re

    t = _re.sub(r"\s+", " ", texto).strip()
    if len(t) <= max_len:
        return t
    corte = t.rfind(" ", 0, max_len - 1)
    return t[: corte if corte > max_len // 2 else max_len - 1] + "…"


def _aviso_to_row(a: BoraAviso, tipo: str | None = None, texto: str | None = None) -> dict[str, Any]:
    """Mapea un BoraAviso (1ª sección) al shape de la tabla `norma`.

    Cuando el listado no trae un sumario legible (vacío, igual al tipo, o un
    código GDE como ``RESOL-2026-276-APN-INASE#MEC``), `texto` (cuerpo del
    detalle) provee el resumen real — sin esto el feed muestra el código pelado.
    El código sí sirve como título canónico, así que solo lo reemplazamos por
    un excerpt cuando no había nada legible (sumario vacío/genérico).
    """
    sumario = (a.sumario or "").strip() or None
    titulo = sumario or a.tipo_linea or f"Aviso {a.aviso_id}"
    resumen = sumario
    if texto and _sumario_sin_valor(a):
        resumen = _texto_excerpt(texto, 1000)
        if not _es_codigo_documento(sumario):
            titulo = _texto_excerpt(texto, 140)
    return {
        "external_id": a.aviso_id,
        "tipo": tipo or a.tipo_slug(),
        "numero": a.numero,
        "titulo": titulo,
        "resumen": resumen,
        "resumen_ia": None,  # lo completa aplicar_resumen_ia() si hay credencial
        "fecha_publicacion": a.fecha,
        "jurisdiccion": "Nacional",
        "sector": a.detect_sector(),
        "organismo": a.organismo,
        "emisor": detect_emisor(a.organismo),
        "estado": "Publicada",
        "impacto": None,
        "bora_seccion": "Primera Sección",
        "entidades": None,
        "tags": None,
        "url": a.url,
        "raw": {k: (v.isoformat() if isinstance(v, date) else v)
                for k, v in dataclasses.asdict(a).items()},
    }


@celery_app.task(name="vigia_workers.tasks.ingest_bora_primera")
def ingest_bora_primera(dry_run: bool = False, lookback_days: int = 5, notify: bool = True) -> dict[str, Any]:
    """Ingesta la 1ª sección del BORA (edición del día + lookback de catch-up).

    El lookback re-scrapea los últimos N días: idempotente (upsert) y
    auto-recupera outages sin task manual. Los DNU salen del BO como
    "Decreto" — se promueven mirando el texto del detalle (art. 99 inc. 3);
    si la heurística falla, InfoLEG corrige al alcanzar (~2 semanas).
    """
    import asyncio as _asyncio
    from datetime import timedelta

    dry = _is_dry_run(dry_run)
    hoy = date.today()
    fechas = [hoy - timedelta(days=d) for d in range(lookback_days)]

    async def _run() -> dict[str, Any]:
        totals = _empty_totals()
        sample: list[dict[str, Any]] = []
        avisos_hoy = 0
        async with BoraClient() as client:
            for fecha in fechas:
                avisos = await client.fetch_seccion("primera", fecha)
                if fecha == hoy:
                    avisos_hoy = len(avisos)
                if not avisos:
                    continue
                # Detalle: para decretos (detección de DNU) y para avisos sin
                # sumario en el listado (título/resumen reales para el feed).
                necesitan_texto = [
                    a for a in avisos if a.tipo_slug() == "DECRETO" or _sumario_sin_valor(a)
                ]
                fetched = await _asyncio.gather(
                    *(client.fetch_detalle_texto(a) for a in necesitan_texto),
                    return_exceptions=True,
                )
                textos = {
                    a.aviso_id: t
                    for a, t in zip(necesitan_texto, fetched)
                    if not isinstance(t, Exception) and t
                }
                es_dnu = {
                    a.aviso_id
                    for a in avisos
                    if a.tipo_slug() == "DECRETO" and looks_like_dnu(textos.get(a.aviso_id))
                }
                rows = [
                    _aviso_to_row(
                        a,
                        tipo="DNU" if a.aviso_id in es_dnu else None,
                        texto=textos.get(a.aviso_id),
                    )
                    for a in avisos
                ]
                if dry:
                    totals["rows"] += len(rows)
                    sample.extend(_dry_sample_row(r) for r in rows[: max(0, _DRY_SAMPLE - len(sample))])
                    continue
                # Síntesis IA (resumen_ia) desde el cuerpo del aviso, donde lo
                # bajamos. No-op si no hay ANTHROPIC_API_KEY; nunca rompe la ingesta.
                await aplicar_resumen_ia(rows, textos)
                _acc(totals, await upsert_normas(BORA_SOURCE, rows))
        if dry:
            return {"rows": totals["rows"], "sample": sample, "avisos_hoy": avisos_hoy}
        return {**totals, "avisos_hoy": avisos_hoy}

    if dry:
        result = run_async(_run())
        return {"source": "bora_primera", "dry_run": True, **result}

    async def _wrapped() -> dict[str, Any]:
        counts = await with_status([BORA_SOURCE["code"]], _run)
        return {"source": "bora_primera", **counts}

    result = run_async(_wrapped())

    # Guard: día hábil sin avisos = probable cambio de HTML (el parser devolvió
    # vacío sin error). Queda visible en /health/sources.
    if result.get("avisos_hoy", 0) == 0 and hoy.weekday() < 5:
        run_async(
            mark_source_run(
                BORA_SOURCE["code"],
                status="warn",
                error="0 avisos en día hábil — ¿feriado o cambió el HTML del listado?",
            )
        )

    # Dedup contra InfoLEG + matching de alertas (frescura inmediata).
    from vigia_workers.reconcile import _reconcile
    result["reconcile"] = run_async(_reconcile())
    from vigia_workers.alerts import _match_all
    result["matching"] = run_async(_match_all(notify=notify))
    return result


def _comunicacion_to_row(c) -> dict[str, Any]:
    """Mapea una ComunicacionBcra al shape de la tabla `norma`.

    El excerpt del body va en `resumen` (peso B del FTS): así una alerta por
    "MULC" o "encaje" matchea el contenido, no solo el título.
    """
    return {
        "external_id": c.external_id,
        "tipo": "COMUNICACION",
        "numero": f"{c.serie} {c.numero}",
        "titulo": c.titulo,
        "resumen": (c.body or "")[:1500] or None,
        "resumen_ia": None,
        "fecha_publicacion": c.fecha,
        "jurisdiccion": "Nacional",
        "sector": c.detect_sector(),
        "organismo": "Banco Central de la República Argentina",
        "emisor": "BCRA",
        "estado": "Publicada",
        "impacto": None,
        "bora_seccion": None,
        "entidades": None,
        "tags": None,
        "url": c.url,
        "raw": {"serie": c.serie, "numero": c.numero,
                "fecha": c.fecha.isoformat() if c.fecha else None},
    }


@celery_app.task(name="vigia_workers.tasks.ingest_bcra_comunicaciones")
def ingest_bcra_comunicaciones(dry_run: bool = False, backfill: int = 0) -> dict[str, Any]:
    """Ingesta Comunicaciones "A" del BCRA (PDFs de numeración secuencial).

    Modo normal: sondea hacia adelante desde el cursor (máximo ya ingestado).
    Primer corrida o `backfill=N`: busca el último número publicado y trae los
    N más recientes (default 300) — correr con match_alertas(notify=False).
    """
    from vigia_connectors import BcraClient
    from sqlalchemy import text as _text
    from vigia_shared.db import session_scope

    dry = _is_dry_run(dry_run)
    SOURCE = catalog_fields("bcra_comunicaciones")

    async def _cursor() -> int | None:
        async with session_scope() as session:
            return await session.scalar(
                _text(
                    "SELECT MAX((raw->>'numero')::int) FROM norma n "
                    "JOIN source_catalog s ON s.id = n.source_id "
                    "WHERE s.code = :code AND n.raw->>'serie' = 'A'"
                ),
                {"code": SOURCE["code"]},
            )

    async def _run() -> dict[str, Any]:
        totals = _empty_totals()
        sample: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        async with BcraClient(serie="A") as client:
            cursor = None if backfill else await _cursor()
            if cursor:
                async for c in client.iter_desde(cursor):
                    rows.append(_comunicacion_to_row(c))
            else:
                latest = await client.find_latest_number()
                if latest is None:
                    raise RuntimeError("BCRA: no se encontró el último número (¿cambió la URL?)")
                count = backfill or 300
                async for c in client.iter_recent(start_number=latest, count=count):
                    rows.append(_comunicacion_to_row(c))
        if dry:
            return {"rows": len(rows), "sample": [_dry_sample_row(r) for r in rows[:_DRY_SAMPLE]]}
        for i in range(0, len(rows), _FULL_BATCH):
            _acc(totals, await upsert_normas(SOURCE, rows[i : i + _FULL_BATCH]))
        return totals

    if dry:
        result = run_async(_run())
        return {"source": SOURCE["code"], "dry_run": True, **result}

    async def _wrapped() -> dict[str, Any]:
        counts = await with_status([SOURCE["code"]], _run)
        return {"source": SOURCE["code"], **counts}

    return run_async(_wrapped())


def _consulta_to_row(c) -> dict[str, Any]:
    """Mapea una ConsultaPublica al shape de `norma` (tipo CONSULTA).

    El estado Abierta→Cerrada lo flipea el re-scrape diario vía upsert.
    """
    return {
        "external_id": c.forum_id,
        "tipo": "CONSULTA",
        "numero": None,
        "titulo": c.titulo,
        "resumen": c.resumen,
        "resumen_ia": None,
        "fecha_publicacion": c.fecha_creacion,
        "jurisdiccion": "Nacional",
        "sector": c.detect_sector(),
        "organismo": c.organismo,
        "emisor": detect_emisor(c.organismo),
        "estado": c.estado(),
        "impacto": None,
        "bora_seccion": None,
        "entidades": None,
        "tags": ["consulta_publica"],
        "url": c.url,
        "raw": {
            "name": c.name,
            "fecha_cierre": c.fecha_cierre.isoformat() if c.fecha_cierre else None,
        },
    }


@celery_app.task(name="vigia_workers.tasks.ingest_consultas_publicas")
def ingest_consultas_publicas(dry_run: bool = False) -> dict[str, Any]:
    """Ingesta consultas públicas (DemocracyOS) — señal regulatoria temprana.

    Volumen ínfimo: se re-scrapea todo en cada corrida (el upsert flipea
    estados de cierre). Una alerta FTS matchea el anteproyecto ANTES de que
    sea norma.
    """
    from vigia_connectors.consultas import ConsultasClient

    dry = _is_dry_run(dry_run)
    SOURCE = catalog_fields("consultas_publicas")

    async def _run() -> dict[str, Any]:
        async with ConsultasClient() as client:
            consultas = await client.fetch_all()
        rows = [_consulta_to_row(c) for c in consultas]
        if dry:
            return {"rows": len(rows), "sample": [_dry_sample_row(r) for r in rows[:_DRY_SAMPLE]]}
        totals = _empty_totals()
        for i in range(0, len(rows), _FULL_BATCH):
            _acc(totals, await upsert_normas(SOURCE, rows[i : i + _FULL_BATCH]))
        return totals

    if dry:
        result = run_async(_run())
        return {"source": SOURCE["code"], "dry_run": True, **result}

    async def _wrapped() -> dict[str, Any]:
        counts = await with_status([SOURCE["code"]], _run)
        return {"source": SOURCE["code"], **counts}

    return run_async(_wrapped())


def _bocaba_to_row(n: BoCabaNorma) -> dict[str, Any]:
    """Mapea un BoCabaNorma al shape de `norma` (jurisdicción CABA)."""
    return {
        "external_id": n.external_id,
        "tipo": n.tipo,
        "numero": n.numero,
        "titulo": n.titulo,
        "resumen": n.sumario,
        "resumen_ia": None,
        "fecha_publicacion": n.fecha,
        "jurisdiccion": "CABA",
        "sector": n.detect_sector(),
        "organismo": n.organismo,
        "emisor": detect_emisor(n.organismo),
        "estado": "Publicada",
        "impacto": None,
        "bora_seccion": None,
        "entidades": None,
        "tags": None,
        "url": n.url,
        "raw": {"nombre": n.nombre, "poder": n.poder, "id_norma": n.id_norma},
    }


@celery_app.task(name="vigia_workers.tasks.ingest_bocaba")
def ingest_bocaba(dry_run: bool = False, dias: int = 5, notify: bool = True) -> dict[str, Any]:
    """Ingesta el Boletín Oficial de CABA (API REST JSON) — últimos `dias`.

    Una llamada por fecha trae todas las publicaciones del día; ingestamos los
    actos normativos (Poderes Legislativo/Ejecutivo/Judicial + Órganos de
    Control) y salteamos edictos, licitaciones y comunicados (avisos).
    """
    dry = _is_dry_run(dry_run)
    SOURCE = catalog_fields("bocaba")

    async def _run() -> dict[str, Any]:
        async with BoCabaClient() as client:
            normas = await client.fetch_recent(dias=dias)
        rows = [_bocaba_to_row(n) for n in normas]
        if dry:
            return {"rows": len(rows), "sample": [_dry_sample_row(r) for r in rows[:_DRY_SAMPLE]]}
        totals = _empty_totals()
        for i in range(0, len(rows), _FULL_BATCH):
            _acc(totals, await upsert_normas(SOURCE, rows[i : i + _FULL_BATCH]))
        return totals

    if dry:
        result = run_async(_run())
        return {"source": SOURCE["code"], "dry_run": True, **result}

    async def _wrapped() -> dict[str, Any]:
        counts = await with_status([SOURCE["code"]], _run)
        return {"source": SOURCE["code"], **counts}

    result = run_async(_wrapped())
    # Tras ingestar, cruzar contra las alertas activas y notificar.
    from vigia_workers.alerts import _match_all
    result["matching"] = run_async(_match_all(notify=notify))
    return result


def _bopba_to_row(n: BoPbaNorma) -> dict[str, Any]:
    """Mapea un BoPbaNorma al shape de `norma` (jurisdicción Buenos Aires)."""
    return {
        "external_id": n.external_id,
        "tipo": n.tipo,
        "numero": n.numero,
        "titulo": n.titulo,
        "resumen": n.resumen,
        "resumen_ia": None,
        "fecha_publicacion": n.fecha,
        "jurisdiccion": "Buenos Aires",
        "sector": n.detect_sector(),
        "organismo": n.organismo,
        "emisor": detect_emisor(n.organismo),
        "estado": "Publicada",
        "impacto": None,
        "bora_seccion": None,
        "entidades": None,
        "tags": None,
        "url": n.url,
        "raw": {"rubro": n.rubro, "numero": n.numero},
    }


@celery_app.task(name="vigia_workers.tasks.ingest_pba")
def ingest_pba(dry_run: bool = False, dias: int = 3, notify: bool = True) -> dict[str, Any]:
    """Ingesta el BO de la Provincia de Buenos Aires (sección OFICIAL, PDF).

    Solo normas (leyes/decretos/resoluciones/disposiciones); saltea societario,
    licitaciones, edictos y las secciones Judicial/Jurisprudencia. Descarga
    pesada (~29 MB por edición): `dias` chico.
    """
    dry = _is_dry_run(dry_run)
    SOURCE = catalog_fields("bopba")

    async def _run() -> dict[str, Any]:
        async with BoPbaClient() as client:
            normas = await client.fetch_recent(dias=dias)
        rows = [_bopba_to_row(n) for n in normas]
        if dry:
            return {"rows": len(rows), "sample": [_dry_sample_row(r) for r in rows[:_DRY_SAMPLE]]}
        totals = _empty_totals()
        for i in range(0, len(rows), _FULL_BATCH):
            _acc(totals, await upsert_normas(SOURCE, rows[i : i + _FULL_BATCH]))
        return totals

    if dry:
        result = run_async(_run())
        return {"source": SOURCE["code"], "dry_run": True, **result}

    async def _wrapped() -> dict[str, Any]:
        counts = await with_status([SOURCE["code"]], _run)
        return {"source": SOURCE["code"], **counts}

    result = run_async(_wrapped())
    from vigia_workers.alerts import _match_all
    result["matching"] = run_async(_match_all(notify=notify))
    return result


@celery_app.task(name="vigia_workers.tasks.ingest_infoleg_full")
def ingest_infoleg_full(dry_run: bool = False) -> dict[str, Any]:
    """Ingesta el corpus completo de InfoLEG (~500k normas) por streaming.

    Descarga el ZIP a un temp file y persiste en batches para no cargar todo
    en memoria.
    """
    dry = _is_dry_run(dry_run)

    async def _run() -> dict[str, Any]:
        totals = _empty_totals()
        sample: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "infoleg_full.zip"
            async with InfoLegClient() as client:
                await client.download_full_zip(dest)
            batch: list[dict[str, Any]] = []
            for norm in InfoLegClient.iter_full_zip(dest):
                row = _norma_to_row(norm)
                if dry:
                    totals["rows"] += 1
                    if len(sample) < _DRY_SAMPLE:
                        sample.append(_dry_sample_row(row))
                    continue
                batch.append(row)
                if len(batch) >= _FULL_BATCH:
                    _acc(totals, await upsert_normas(INFOLEG_SOURCE, batch))
                    batch = []
            if batch:
                _acc(totals, await upsert_normas(INFOLEG_SOURCE, batch))
        if dry:
            return {"rows": totals["rows"], "sample": sample}
        return totals

    if dry:
        result = run_async(_run())
        return {"source": "infoleg", "mode": "full", "dry_run": True, **result}

    async def _wrapped() -> dict[str, Any]:
        counts = await with_status([INFOLEG_SOURCE["code"]], _run)
        return {"source": "infoleg", "mode": "full", **counts}

    return run_async(_wrapped())


@celery_app.task(name="vigia_workers.tasks.backfill_emisores")
def backfill_emisores() -> dict[str, Any]:
    """Rellena `norma.emisor` en el histórico (la ingesta nueva ya lo setea).

    Idempotente: solo toca filas con emisor NULL. Pagina por id para no cargar
    todo el corpus en memoria. Re-correrla reescanea los NULL (barato).
    """
    from sqlalchemy import text as _text
    from vigia_shared.db import session_scope

    async def _run() -> dict[str, Any]:
        scanned = 0
        updated = 0
        last_id = 0
        async with session_scope() as session:
            while True:
                rows = (
                    await session.execute(
                        _text(
                            "SELECT id, organismo FROM norma "
                            "WHERE emisor IS NULL AND organismo IS NOT NULL AND id > :last "
                            "ORDER BY id LIMIT 5000"
                        ),
                        {"last": last_id},
                    )
                ).all()
                if not rows:
                    break
                scanned += len(rows)
                last_id = rows[-1][0]
                payload = [
                    {"id": nid, "em": em}
                    for nid, org in rows
                    if (em := detect_emisor(org))
                ]
                if payload:
                    await session.execute(
                        _text("UPDATE norma SET emisor = :em WHERE id = :id"), payload
                    )
                    updated += len(payload)
        return {"scanned": scanned, "updated": updated}

    return run_async(_run())
