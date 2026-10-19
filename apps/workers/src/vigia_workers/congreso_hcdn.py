"""Congreso — ingesta de Diputados → tablas propias de la sección Congreso.

Nada de esto entra a `norma`: legisladores, sesiones, asuntos tratados y agenda
de comisiones van a `legislador`, `congreso_sesion`, `asunto_tratado` y
`reunion_comision` (migración 0012), igual que el Radar societario. El cruce
con los proyectos es por expediente canónico (`vigia_shared.expedientes`).

Diputados va SIN voto nominal: `votaciones.hcdn.gob.ar` tiene reCAPTCHA v3 (no
se esquiva) y el dataset CKAN `votaciones_nominales` se cortó en feb-2020. Lo
que hay es el resultado por expediente del Boletín de Asuntos Tratados.

Tasks (todas aceptan `dry_run` o `VIGIA_INGEST_DRY_RUN=1`, que no toca la base):
- `ingest_hcdn_legisladores`: semanal. CKAN `legisladores`; marca `activo=false`
  a quien ya no está en la Composición Actual.
- `ingest_hcdn_sesiones`: diaria. CKAN `sesiones` (2008→) + listado del sitio.
- `ingest_hcdn_asuntos(periodos=...)`: diaria. Baja el BAT de las sesiones
  recientes; con `periodos=[143, 142]` hace backfill de esos períodos.
- `ingest_hcdn_agenda`: dos veces por día. Semana en curso de comisiones.

El CKAN de HCDN limita la tasa: todo es secuencial, nunca en paralelo.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert

from vigia_connectors.hcdn import (
    LEGISLADORES_PACKAGE_ID,
    RECURSO_COMPOSICION,
    RECURSO_MANDATOS,
    SESIONES_PACKAGE_ID,
    HcdnClient,
    HcdnLegislador,
    legisladores_vigentes,
)
from vigia_connectors.hcdn_actividad import (
    ART,
    HcdnActividadClient,
    HcdnAsunto,
    HcdnReunion,
    HcdnSesion,
    combinar_sesiones,
    en_receso,
)
from vigia_shared.db import session_scope
from vigia_shared.models import AsuntoTratado, CongresoSesion, Legislador, ReunionComision
from vigia_workers.celery_app import celery_app
from vigia_workers.persistence import ensure_source, mark_source_run, run_async, with_status

CAMARA = "D"
_BATCH = 500

# Diputados tiene 257 bancas. Si la nómina llega mucho más corta, es el CSV
# que vino roto, no una renuncia masiva: no se desactiva a nadie.
_MIN_NOMINA = 200
# Un BAT vacío es normal los primeros días después de la sesión.
_BAT_GRACIA_DIAS = 7
_ASUNTOS_LOOKBACK_DIAS = 30


def _dry(dry_run: bool) -> bool:
    return dry_run or os.environ.get("VIGIA_INGEST_DRY_RUN", "").strip().lower() in ("1", "true", "yes")


def _hoy_art() -> date:
    return datetime.now(ART).date()


def _corte(s: str | None, n: int) -> str | None:
    return s[:n] if s else None


# ─────────────────────────────────── Mappers ───────────────────────────────────
# Un dict por fila con exactamente las columnas que escribe el upsert (sin id,
# timestamps ni search_vector, que es GENERATED). Shape-tests en
# apps/workers/tests/test_congreso_hcdn.py.


def _legislador_to_row(l: HcdnLegislador) -> dict[str, Any]:
    return {
        "camara": CAMARA,
        "external_id": l.external_id,
        "nombre": l.nombre[:255],
        "bloque": _corte(l.bloque, 255),
        "distrito": _corte(l.distrito, 128),
        "mandato_desde": l.mandato_desde,
        "mandato_hasta": l.mandato_hasta,
        "activo": True,
        "raw": l.raw,
    }


def _sesion_to_row(s: HcdnSesion) -> dict[str, Any]:
    return {
        "camara": CAMARA,
        "external_id": s.external_id,
        "fecha": s.fecha,
        "tipo": s.tipo,
        "periodo": s.periodo,
        "reunion": s.reunion,
        "numero_sesion": s.numero_sesion,
        "url": s.url,
        "url_taquigrafica": None,
        "url_diario": None,
        "raw": s.raw,
    }


def _asunto_to_row(a: HcdnAsunto, sesion_id: int) -> dict[str, Any]:
    return {
        "camara": CAMARA,
        "sesion_id": sesion_id,
        "clave": a.clave,
        "expedientes": a.expedientes,
        "orden_del_dia": a.orden_del_dia,
        "tipo": a.tipo,
        "sumario": a.sumario,
        "resultado": a.resultado,
        "raw": {"orden": a.orden, "detalle": a.detalle, "links": a.links},
    }


def _reunion_to_row(r: HcdnReunion) -> dict[str, Any]:
    return {
        "camara": CAMARA,
        "external_id": r.external_id,
        "fecha_hora": r.fecha_hora,
        "comision": r.comision,
        "sala": _corte(r.sala, 255),
        "tipo": _corte(r.tipo, 128),
        "temario": r.temario,
        "expedientes": r.expedientes,
        "url_citacion": r.url_citacion,
        "raw": {
            "reun_id": r.reun_id,
            "comisiones": r.comisiones,
            "slugs": r.slugs,
            "leyenda": r.leyenda,
        },
    }


# ─────────────────────────────────── Upserts ───────────────────────────────────


async def _upsert(model, rows: list[dict], keys: tuple[str, ...], *, touch: bool = False) -> int:
    """Upsert por `keys` en lotes de 500 (pg insert + dicts: `search_vector` es
    GENERATED y no puede ir en el INSERT). Dedup intra-lote porque ON CONFLICT
    no tolera dos filas con la misma clave en un mismo statement."""
    if not rows:
        return 0
    deduped = {tuple(r[k] for k in keys): r for r in rows}
    rows = list(deduped.values())
    cols = [c for c in rows[0] if c not in keys]
    n = 0
    async with session_scope() as session:
        for i in range(0, len(rows), _BATCH):
            stmt = insert(model).values(rows[i : i + _BATCH])
            set_ = {c: getattr(stmt.excluded, c) for c in cols}
            if touch:
                set_["updated_at"] = func.now()
            stmt = stmt.on_conflict_do_update(index_elements=list(keys), set_=set_)
            res = await session.execute(stmt)
            n += res.rowcount or 0
    return n


# ──────────────────────────────── Legisladores ────────────────────────────────


async def _ingest_legisladores(dry: bool) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        mand = Path(tmp) / "mandatos.csv"
        comp = Path(tmp) / "composicion.csv"
        async with HcdnClient() as client:
            # Secuencial a propósito: el CKAN de HCDN corta las ráfagas.
            await client.download_csv(comp, LEGISLADORES_PACKAGE_ID, RECURSO_COMPOSICION)
            await client.download_csv(mand, LEGISLADORES_PACKAGE_ID, RECURSO_MANDATOS)
        actuales = list(HcdnClient.iter_composicion_csv(comp))
        mandatos = list(HcdnClient.iter_mandatos_csv(mand))
    legs, sin_id = legisladores_vigentes(mandatos, actuales, _hoy_art())
    rows = [_legislador_to_row(l) for l in legs]
    out: dict[str, Any] = {
        "composicion": len(actuales),
        "con_id": len(rows),
        "sin_id": [f"{a.apellido}, {a.nombre} ({a.distrito})" for a in sin_id],
    }
    if dry:
        out["sample"] = [
            {k: r[k] for k in ("external_id", "nombre", "bloque", "distrito")} for r in rows[:5]
        ]
        return out
    await _upsert(Legislador, rows, ("camara", "external_id"), touch=True)
    if len(rows) >= _MIN_NOMINA:
        async with session_scope() as session:
            res = await session.execute(
                text(
                    "UPDATE legislador SET activo = false, updated_at = now() "
                    "WHERE camara = :c AND activo AND NOT (external_id = ANY(:ids))"
                ),
                {"c": CAMARA, "ids": [r["external_id"] for r in rows]},
            )
            out["desactivados"] = res.rowcount or 0
    else:
        out["desactivados"] = 0
        out["nomina_corta"] = True
    return out


@celery_app.task(name="vigia_workers.congreso_hcdn.ingest_hcdn_legisladores")
def ingest_hcdn_legisladores(dry_run: bool = False) -> dict[str, Any]:
    code = "hcdn_legisladores"
    if _dry(dry_run):
        return {"source": code, "dry_run": True, **run_async(_ingest_legisladores(True))}

    async def _wrapped() -> dict[str, Any]:
        await ensure_source(code)
        return await with_status([code], lambda: _ingest_legisladores(False))

    result = run_async(_wrapped())
    avisos = []
    if result.get("sin_id"):
        avisos.append(
            f"{len(result['sin_id'])} diputados de la Composición Actual sin ID en el histórico "
            f"(no se ingirieron): {', '.join(result['sin_id'][:5])}"
        )
    if result.get("nomina_corta"):
        avisos.append(
            f"nómina de {result['con_id']} diputados (< {_MIN_NOMINA}): no se desactivó a nadie"
        )
    if avisos:
        run_async(mark_source_run(code, status="warn", error=" · ".join(avisos)[:1000]))
    return {"source": code, **result}


# ─────────────────────────────────── Sesiones ───────────────────────────────────


async def _sesiones_combinadas() -> tuple[list[HcdnSesion], dict[str, Any]]:
    """CKAN + sitio. El CKAN es opcional: si se cae, el listado del sitio alcanza
    (trae todas las sesiones desde 1983, solo le faltan las horas)."""
    info: dict[str, Any] = {}
    csv_rows = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "sesiones.csv"
            async with HcdnClient() as client:
                await client.download_csv(dest, SESIONES_PACKAGE_ID)
            csv_rows = list(HcdnClient.iter_sesiones_csv(dest))
    except Exception as exc:  # noqa: BLE001 — se reporta como warn
        info["ckan_error"] = f"{type(exc).__name__}: {exc}".strip()[:300]
    async with HcdnActividadClient() as web:
        sitio, descartadas = await web.fetch_sesiones_listado()
    sesiones, desfase = combinar_sesiones(csv_rows, sitio)
    info.update({
        "csv": len(csv_rows),
        "sitio": len(sitio),
        "sitio_descartadas": descartadas,
        "desfase_csv_dias": desfase,
    })
    return sesiones, info


async def _ingest_sesiones(dry: bool) -> dict[str, Any]:
    sesiones, info = await _sesiones_combinadas()
    rows = [_sesion_to_row(s) for s in sesiones]
    out = {"rows": len(rows), **info}
    if dry:
        out["sample"] = [
            {k: (v.isoformat() if isinstance(v, date) else v) for k, v in r.items() if k != "raw"}
            for r in sorted(rows, key=lambda r: r["fecha"], reverse=True)[:5]
        ]
        return out
    await _upsert(CongresoSesion, rows, ("camara", "external_id"))
    return out


@celery_app.task(name="vigia_workers.congreso_hcdn.ingest_hcdn_sesiones")
def ingest_hcdn_sesiones(dry_run: bool = False) -> dict[str, Any]:
    code = "hcdn_sesiones"
    if _dry(dry_run):
        return {"source": code, "dry_run": True, **run_async(_ingest_sesiones(True))}

    async def _wrapped() -> dict[str, Any]:
        await ensure_source(code)
        return await with_status([code], lambda: _ingest_sesiones(False))

    result = run_async(_wrapped())
    if result.get("ckan_error"):
        run_async(mark_source_run(
            code, status="warn",
            error=f"dataset CKAN `sesiones` no disponible, solo listado del sitio: {result['ckan_error']}",
        ))
    return {"source": code, **result}


# ─────────────────────────────── Asuntos tratados ───────────────────────────────


def sesiones_a_recorrer(
    sesiones: list[HcdnSesion], hoy: date, *, periodos: list[int] | None = None,
    lookback_dias: int = _ASUNTOS_LOOKBACK_DIAS,
) -> list[HcdnSesion]:
    """Las sesiones cuyo BAT hay que bajar: las de los últimos `lookback_dias`
    (el boletín se publica días después y a veces se corrige) y, si se pasan
    `periodos`, todas las de esos períodos (backfill). Nunca asambleas (no
    tienen boletín) ni sesiones futuras."""
    desde = hoy - timedelta(days=lookback_dias)
    per = set(periodos or [])
    return [
        s for s in sesiones
        if not s.asamblea and s.fecha <= hoy and (s.fecha >= desde or s.periodo in per)
    ]


async def _sesion_ids(external_ids: list[str]) -> dict[str, int]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                text("SELECT external_id, id FROM congreso_sesion WHERE camara = :c AND external_id = ANY(:ids)"),
                {"c": CAMARA, "ids": external_ids},
            )
        ).all()
    return {r[0]: r[1] for r in rows}


async def _reemplazar_asuntos(sesion_id: int, rows: list[dict]) -> None:
    """Upsert de los asuntos de UNA sesión y baja de los que ya no figuran (el
    BAT se corrige; las claves por orden `#n` se corren si se agrega una fila)."""
    await _upsert(AsuntoTratado, rows, ("sesion_id", "clave"))
    async with session_scope() as session:
        await session.execute(
            text("DELETE FROM asunto_tratado WHERE sesion_id = :s AND NOT (clave = ANY(:claves))"),
            {"s": sesion_id, "claves": [r["clave"] for r in rows]},
        )


async def _ingest_asuntos(dry: bool, periodos: list[int] | None, lookback_dias: int) -> dict[str, Any]:
    hoy = _hoy_art()
    async with HcdnActividadClient() as web:
        sitio, _ = await web.fetch_sesiones_listado()
        # Solo el listado (sin CKAN): alcanza para periodo/reunión/sesión y
        # ahorra un hit al CKAN, que limita la tasa.
        sesiones, _ = combinar_sesiones([], sitio)
        objetivo = sesiones_a_recorrer(sesiones, hoy, periodos=periodos, lookback_dias=lookback_dias)

        ids: dict[str, int] = {}
        if not dry and objetivo:
            # Garantiza la FK aunque `ingest_hcdn_sesiones` todavía no haya
            # corrido hoy. DO NOTHING: no pisar las horas que trae el CKAN.
            async with session_scope() as session:
                stmt = insert(CongresoSesion).values([_sesion_to_row(s) for s in objetivo])
                await session.execute(stmt.on_conflict_do_nothing(index_elements=["camara", "external_id"]))
            ids = await _sesion_ids([s.external_id for s in objetivo])

        total, con_bat, pendientes = 0, 0, []
        sin_bat: list[str] = []
        sample: list[dict] = []
        for s in objetivo:
            asuntos = await web.fetch_bat(s.bat_url)
            if not asuntos:
                if (hoy - s.fecha).days > _BAT_GRACIA_DIAS:
                    sin_bat.append(s.external_id)
                else:
                    pendientes.append(s.external_id)
                continue
            con_bat += 1
            total += len(asuntos)
            if dry:
                sample.extend(
                    {"sesion": s.external_id, "clave": a.clave, "resultado": a.resultado,
                     "expedientes": a.expedientes, "sumario": a.sumario[:120]}
                    for a in asuntos[: max(0, 6 - len(sample))]
                )
                continue
            await _reemplazar_asuntos(ids[s.external_id], [_asunto_to_row(a, ids[s.external_id]) for a in asuntos])

    out: dict[str, Any] = {
        "sesiones": len(objetivo),
        "con_bat": con_bat,
        "asuntos": total,
        "pendientes": pendientes,
        "sin_bat": sin_bat,
    }
    if dry:
        out["sample"] = sample
    return out


@celery_app.task(name="vigia_workers.congreso_hcdn.ingest_hcdn_asuntos")
def ingest_hcdn_asuntos(
    dry_run: bool = False,
    periodos: list[int] | None = None,
    lookback_dias: int = _ASUNTOS_LOOKBACK_DIAS,
) -> dict[str, Any]:
    code = "hcdn_asuntos"
    if _dry(dry_run):
        return {"source": code, "dry_run": True,
                **run_async(_ingest_asuntos(True, periodos, lookback_dias))}

    async def _wrapped() -> dict[str, Any]:
        await ensure_source(code)
        return await with_status([code], lambda: _ingest_asuntos(False, periodos, lookback_dias))

    result = run_async(_wrapped())
    # Una sesión vieja sin boletín es cierta pero no necesariamente un error
    # (las "expresiones en minoría" a veces no lo tienen): warn, no stale.
    if result.get("sin_bat"):
        run_async(mark_source_run(
            code, status="warn",
            error=(
                f"{len(result['sin_bat'])} sesiones de hace más de {_BAT_GRACIA_DIAS} días sin "
                f"Boletín de Asuntos Tratados parseable: {', '.join(result['sin_bat'][:10])}"
            ),
        ))
    return {"source": code, **result}


# ──────────────────────────────── Agenda de comisiones ────────────────────────────────


def agenda_vacia_sospechosa(n_reuniones: int, hoy: date) -> bool:
    """Agenda sin reuniones un lunes-jueves fuera de receso: algo cambió en la
    página (los viernes y findes la tabla puede venir vacía o ya con la semana
    siguiente)."""
    return n_reuniones == 0 and hoy.weekday() <= 3 and not en_receso(hoy)


# Una reunión suspendida o reprogramada desaparece de la agenda, y sin esto
# quedaría en la tabla como si se fuera a hacer (y, si no tenía reunId, la
# reprogramada entra con otro hash y la vieja queda duplicada). Solo se borra
# el FUTURO de los días que la página mostró: el pasado ya no figura en la
# agenda y no por eso dejó de pasar.
_BAJAS_AGENDA_SQL = """
DELETE FROM reunion_comision
WHERE camara = :c
  AND fecha_hora >= :ahora
  AND (fecha_hora AT TIME ZONE 'America/Argentina/Buenos_Aires')::date = ANY(:dias)
  AND NOT (external_id = ANY(:ids))
"""


def bajas_agenda(dias: list[date], ids: list[str], ahora: datetime) -> dict[str, Any] | None:
    """Parámetros de `_BAJAS_AGENDA_SQL`, o None si no hay que borrar nada.

    Sin `dias` la página vino rota o vacía (eso ya lo avisa el warn de agenda
    vacía): no se interpreta como "se suspendió todo".

    Los días cubiertos son TODOS los que van de hoy al último que muestra la
    página, no solo los que tienen encabezado: un día cuya única reunión se
    suspendió desaparece de la agenda, y si contáramos solo los que figuran, la
    suspendida quedaría para siempre. Lo posterior al último día no se toca.
    """
    if not dias:
        return None
    hoy = ahora.astimezone(ART).date()
    fin = max(dias)
    if fin < hoy:
        return None
    cubiertos = [hoy + timedelta(days=i) for i in range((fin - hoy).days + 1)]
    return {"c": CAMARA, "ahora": ahora, "dias": cubiertos, "ids": sorted(set(ids))}


async def _ingest_agenda(dry: bool) -> dict[str, Any]:
    async with HcdnActividadClient() as web:
        agenda = await web.fetch_agenda()
    rows = [_reunion_to_row(r) for r in agenda.reuniones]
    out: dict[str, Any] = {
        "rows": len(rows),
        "dias": [d.isoformat() for d in agenda.dias],
        "recinto": len(agenda.recinto),
        "con_expedientes": sum(1 for r in rows if r["expedientes"]),
    }
    if dry:
        out["sample"] = [
            {"external_id": r["external_id"], "fecha_hora": r["fecha_hora"].isoformat(),
             "comision": r["comision"], "tipo": r["tipo"], "expedientes": r["expedientes"]}
            for r in rows[:5]
        ]
        return out
    await _upsert(ReunionComision, rows, ("camara", "external_id"))
    out["bajas"] = 0
    params = bajas_agenda(agenda.dias, [r["external_id"] for r in rows], datetime.now(ART))
    if params is not None:
        async with session_scope() as session:
            res = await session.execute(text(_BAJAS_AGENDA_SQL), params)
            out["bajas"] = res.rowcount or 0
    return out


@celery_app.task(name="vigia_workers.congreso_hcdn.ingest_hcdn_agenda")
def ingest_hcdn_agenda(dry_run: bool = False) -> dict[str, Any]:
    code = "hcdn_agenda"
    if _dry(dry_run):
        return {"source": code, "dry_run": True, **run_async(_ingest_agenda(True))}

    async def _wrapped() -> dict[str, Any]:
        await ensure_source(code)
        return await with_status([code], lambda: _ingest_agenda(False))

    result = run_async(_wrapped())
    hoy = _hoy_art()
    if agenda_vacia_sospechosa(result.get("rows", 0), hoy):
        run_async(mark_source_run(
            code, status="warn",
            error=f"agenda de comisiones vacía el {hoy.isoformat()} (día hábil fuera de receso)",
        ))
    return {"source": code, **result}

