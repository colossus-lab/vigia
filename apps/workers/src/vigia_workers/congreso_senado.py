"""Actividad del Senado → tablas del Congreso (migración 0012).

Votaciones con voto nominal, agenda de comisiones, sesiones y senadores. Nada
de esto entra a `norma` (mismo criterio que `aviso_societario`): la actividad
se cruza con los proyectos por expediente canónico (`norma.expedientes &&
votacion.expedientes`), no viviendo en la misma tabla.

Inserts con `pg insert` y dicts, nunca objetos ORM: `votacion.search_vector` y
`reunion_comision.search_vector` son GENERATED y el ORM mandaría la columna.

Fuentes en el registry (`vigia_shared.sources`): `senado_votaciones`,
`senado_agenda`, `senado_sesiones`, `senado_legisladores`.
"""
from __future__ import annotations

import dataclasses
import os
from collections.abc import Callable, Iterable
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert

from vigia_connectors.senado_actividad import (
    ART,
    ActaDetalle,
    ActaListado,
    IndiceSenadores,
    ReunionAgenda,
    SenadoActividadClient,
    Senador,
    SesionTac,
    VotoNominal,
    id_sintetico,
)
from vigia_shared.db import session_scope
from vigia_shared.models import CongresoSesion, Legislador, ReunionComision, Votacion, Voto
from vigia_workers.celery_app import celery_app
from vigia_workers.persistence import ensure_source, mark_source_run, run_async, with_status

_BATCH = 500
_CAMARA = "S"
_DRY_SAMPLE = 5

# Primer año del backfill de votaciones: empata con `sesiones` de HCDN (2008→).
# El Senado tiene actas desde 1983 si alguna vez hace falta ir más atrás.
ANIO_BACKFILL = 2008

# Menos que esto en el listado de senadores en ejercicio (son 72) es un parseo
# roto o una respuesta a medias, no una renovación: no se desactiva a nadie.
_MIN_SENADORES = 60

# Ex senadores del histórico que vale la pena tener: los de la democracia actual.
_DESDE_HISTORICO = date(1983, 12, 10)


def _dry(flag: bool) -> bool:
    return flag or os.environ.get("VIGIA_INGEST_DRY_RUN", "").strip().lower() in ("1", "true", "yes")


def _jsonable(v: Any) -> Any:
    if isinstance(v, datetime | date):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [_jsonable(x) for x in v]
    return v


def _hoy() -> date:
    return datetime.now(ART).date()


# ---------------------------------------------------------------------------
# mappers (puros: los shape-tests viven en tests/test_mappers.py)
# ---------------------------------------------------------------------------

def _senador_to_row(s: Senador, *, activo: bool) -> dict[str, Any]:
    return {
        "camara": _CAMARA,
        "external_id": s.external_id,
        "nombre": s.nombre[:255],
        "bloque": (s.bloque or s.partido or None),
        "distrito": s.distrito,
        "mandato_desde": s.mandato_desde,
        "mandato_hasta": s.mandato_hasta,
        "activo": activo,
        "raw": _jsonable(s.raw),
    }


def _historico_a_senadores(periodos: Iterable[Senador], excluir: set[str]) -> list[Senador]:
    """Colapsa el histórico (una fila por período) a un senador por ID.

    Nombre, provincia y partido salen del período más reciente; el mandato va
    del primer inicio al último cese. Quedan afuera los que hoy están en
    ejercicio (`excluir`) y los que dejaron la banca antes de 1983.
    """
    por_id: dict[str, list[Senador]] = {}
    for p in periodos:
        if p.external_id not in excluir:
            por_id.setdefault(p.external_id, []).append(p)
    out: list[Senador] = []
    for sid, ps in por_id.items():
        ps.sort(key=lambda p: p.mandato_desde or date.min)
        ultimo = ps[-1]
        hasta = max((p.mandato_hasta for p in ps if p.mandato_hasta), default=None)
        if hasta is not None and hasta < _DESDE_HISTORICO:
            continue
        out.append(Senador(
            external_id=sid,
            nombre=ultimo.nombre,
            distrito=ultimo.distrito,
            bloque=None,
            partido=ultimo.partido,
            mandato_desde=next((p.mandato_desde for p in ps if p.mandato_desde), None),
            mandato_hasta=hasta,
            raw={"periodos": [p.raw for p in ps]},
        ))
    return out


def _votacion_to_row(listado: ActaListado | None, detalle: ActaDetalle | None) -> dict[str, Any]:
    """Una votación desde su fila del listado, su detalle, o ambos.

    El detalle manda (trae la hora y los totales); el listado aporta el PDF, el
    video y es el respaldo cuando el detalle no se pudo bajar en esta corrida.
    """
    if listado is None and detalle is None:
        raise ValueError("hace falta el listado o el detalle")
    base = detalle or listado
    if detalle is not None:
        fecha = detalle.fecha
    else:
        fecha = datetime(listado.fecha.year, listado.fecha.month, listado.fecha.day, tzinfo=ART)

    def primero(*vals: Any) -> Any:
        return next((v for v in vals if v not in (None, "", [])), None)

    expedientes = list(dict.fromkeys(
        (detalle.expedientes if detalle else []) + (listado.expedientes if listado else [])
    ))
    ordenes = list(dict.fromkeys(
        (detalle.ordenes_del_dia if detalle else []) + (listado.ordenes_del_dia if listado else [])
    ))
    raw: dict[str, Any] = {}
    if listado is not None:
        raw["listado"] = _jsonable(dataclasses.asdict(listado))
    if detalle is not None:
        raw["detalle"] = _jsonable({
            k: v for k, v in dataclasses.asdict(detalle).items() if k != "votos"
        })
    return {
        "camara": _CAMARA,
        "external_id": base.acta_id,
        "fecha": fecha,
        "numero_acta": primero(detalle and detalle.numero_acta, listado and listado.numero_acta),
        "titulo": primero(detalle and detalle.titulo, listado and listado.titulo) or "(sin título)",
        "etapa": primero(detalle and detalle.etapa, listado and listado.etapa),
        "mayoria": primero(detalle and detalle.mayoria, listado and listado.mayoria),
        "resultado": primero(detalle and detalle.resultado, listado and listado.resultado),
        "afirmativos": detalle.afirmativos if detalle else None,
        "negativos": detalle.negativos if detalle else None,
        "abstenciones": detalle.abstenciones if detalle else None,
        "ausentes": detalle.ausentes if detalle else None,
        "expedientes": expedientes,
        "ordenes_del_dia": ordenes,
        "url": (listado.url if listado else
                f"https://www.senado.gob.ar/votaciones/detalleActa/{base.acta_id}"),
        "url_pdf": listado.url_pdf if listado else None,
        "video_url": listado.video_url if listado else None,
        "raw": raw,
    }


def _legislador_desde_voto(v: VotoNominal, external_id: str) -> dict[str, Any]:
    """Alta mínima de un senador que aparece en un acta y no está en `legislador`.

    Con link al perfil es alguien en ejercicio (el Senado solo linkea a esos);
    `ingest_senado_legisladores` lo completa en la corrida semanal.
    """
    return {
        "camara": _CAMARA,
        "external_id": external_id,
        "nombre": v.nombre[:255] or "(sin nombre)",
        "bloque": v.bloque,
        "distrito": v.distrito,
        "activo": v.senador_id is not None,
        "raw": {"origen": "acta", "nombre": v.nombre},
    }


def _voto_to_row(votacion_id: int, legislador_id: int, v: VotoNominal) -> dict[str, Any]:
    # Bloque y provincia del acta: son los del momento de votar, no los de hoy.
    return {
        "votacion_id": votacion_id,
        "legislador_id": legislador_id,
        "voto": v.voto,
        "bloque": v.bloque,
        "distrito": v.distrito,
    }


def _reunion_to_row(r: ReunionAgenda) -> dict[str, Any]:
    return {
        "camara": _CAMARA,
        "external_id": r.external_id,
        "fecha_hora": r.fecha_hora,
        "comision": r.comision[:512],
        "sala": r.sala,
        "tipo": r.tipo,
        "temario": r.temario,
        "expedientes": r.expedientes,
        "url_citacion": None,  # el Senado no publica PDF de citación en la agenda
        "raw": _jsonable(r.raw),
    }


def _sesion_to_row(s: SesionTac) -> dict[str, Any]:
    return {
        "camara": _CAMARA,
        "external_id": s.external_id,
        "fecha": s.fecha,
        "tipo": s.tipo,
        # El período parlamentario no sale de la tabla y no se deduce del año:
        # las extraordinarias de enero/febrero son del período anterior.
        "periodo": None,
        "reunion": s.reunion,
        "numero_sesion": s.numero_sesion,
        "url": s.url_taquigrafica or s.url_diario,
        "url_taquigrafica": s.url_taquigrafica,
        "url_diario": s.url_diario,
        "raw": _jsonable(dataclasses.asdict(s)),
    }


# ---------------------------------------------------------------------------
# persistencia
# ---------------------------------------------------------------------------

async def _upsert(
    model: Any,
    rows: list[dict[str, Any]],
    *,
    conflicto: list[str],
    actualizar: Iterable[str],
    extra_set: dict[str, Any] | Callable[[Any], dict[str, Any]] | None = None,
    returning: tuple[Any, ...] | None = None,
) -> list[Any]:
    """Upsert en lotes de `_BATCH` con dedup intra-lote (ON CONFLICT no tolera
    dos filas con la misma clave en un mismo INSERT)."""
    vistos: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        vistos[tuple(r[c] for c in conflicto)] = r
    rows = list(vistos.values())
    out: list[Any] = []
    if not rows:
        return out
    cols = list(actualizar)
    async with session_scope() as session:
        for i in range(0, len(rows), _BATCH):
            stmt = insert(model).values(rows[i : i + _BATCH])
            set_ = {c: getattr(stmt.excluded, c) for c in cols}
            if extra_set:
                set_.update(extra_set(stmt) if callable(extra_set) else extra_set)
            stmt = stmt.on_conflict_do_update(index_elements=conflicto, set_=set_)
            if returning:
                stmt = stmt.returning(*returning)
                out.extend((await session.execute(stmt)).fetchall())
            else:
                await session.execute(stmt)
    return out


async def _actas_con_votos() -> set[str]:
    """Actas ya cerradas: las que tienen voto nominal guardado.

    Un acta guardada sin votos (detalle caído, o el Senado todavía no cargó el
    nominal) se vuelve a pedir: si no, quedaría vacía para siempre.
    """
    async with session_scope() as session:
        rows = (await session.execute(text(
            "SELECT v.external_id FROM votacion v WHERE v.camara = :c "
            "AND EXISTS (SELECT 1 FROM voto WHERE voto.votacion_id = v.id)"
        ), {"c": _CAMARA})).scalars().all()
    return set(rows)


async def _ids_legisladores(external_ids: Iterable[str]) -> dict[str, int]:
    ids = list(set(external_ids))
    if not ids:
        return {}
    async with session_scope() as session:
        rows = (await session.execute(text(
            "SELECT external_id, id FROM legislador WHERE camara = :c AND external_id = ANY(:ids)"
        ), {"c": _CAMARA, "ids": ids})).all()
    return {r[0]: r[1] for r in rows}


async def _asegurar_legisladores(minimos: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Da de alta los que falten (sin pisar a los existentes) y devuelve external_id → id."""
    existentes = await _ids_legisladores(minimos)
    faltan = [row for eid, row in minimos.items() if eid not in existentes]
    if faltan:
        async with session_scope() as session:
            for i in range(0, len(faltan), _BATCH):
                stmt = insert(Legislador).values(faltan[i : i + _BATCH])
                await session.execute(stmt.on_conflict_do_nothing(
                    index_elements=["camara", "external_id"]
                ))
        existentes = await _ids_legisladores(minimos)
    return existentes


async def _vincular_sesiones() -> int:
    """`votacion.sesion_id` por fecha. La fecha del acta casi siempre es la de
    la sesión (aunque la votación sea de madrugada), así que alcanza con el día.

    Casi: hay sesiones que cruzan la medianoche con el acta fechada al día
    siguiente (el SIPA, sesión del 20/11/2008, actas del 21/11). Por eso, si ese
    día no hubo sesión, vale la del día anterior. Si hubo más de una, gana la
    del mismo día, después la que no es asamblea ni juicio político y después
    la de número de reunión más alto (la última del día).
    """
    async with session_scope() as session:
        res = await session.execute(text("""
            WITH dia AS (
                SELECT v.id, (v.fecha AT TIME ZONE 'America/Argentina/Buenos_Aires')::date AS d
                FROM votacion v
                WHERE v.camara = :c AND v.sesion_id IS NULL
            ), elegida AS (
                SELECT DISTINCT ON (dia.id) dia.id AS votacion_id, s.id AS sesion_id
                FROM dia
                JOIN congreso_sesion s
                  ON s.camara = :c AND s.fecha BETWEEN dia.d - 1 AND dia.d
                ORDER BY dia.id, (s.fecha = dia.d) DESC,
                         (s.tipo ILIKE ANY(:secundarias)), s.reunion DESC NULLS LAST
            )
            UPDATE votacion v SET sesion_id = e.sesion_id
            FROM elegida e WHERE v.id = e.votacion_id
        """), {"c": _CAMARA, "secundarias": ["ASAMBLEA%", "TRIBUNAL%"]})
        return res.rowcount or 0


# ---------------------------------------------------------------------------
# votaciones
# ---------------------------------------------------------------------------

def _resolver_ids(
    detalles: Iterable[ActaDetalle], indice: IndiceSenadores | None
) -> tuple[dict[tuple[str, int], str], dict[str, int]]:
    """external_id del Senado para cada fila de voto (acta, posición).

    Con link, el del link. Sin link (ex senadores), por nombre + provincia +
    fecha contra el histórico. Si ni así aparece, un ID sintético estable
    (`nom-...`): el voto no se pierde y el senador queda identificable.
    """
    out: dict[tuple[str, int], str] = {}
    stats = {"por_link": 0, "por_indice": 0, "sinteticos": 0}
    for d in detalles:
        for i, v in enumerate(d.votos):
            if v.senador_id:
                out[(d.acta_id, i)] = v.senador_id
                stats["por_link"] += 1
                continue
            eid = indice.resolver(v.nombre, v.distrito, d.fecha.date()) if indice else None
            if eid:
                stats["por_indice"] += 1
            else:
                eid = id_sintetico(v.nombre, v.distrito)
                stats["sinteticos"] += 1
            out[(d.acta_id, i)] = eid
    return out, stats


async def _guardar_anio(
    listado: list[ActaListado], detalles: dict[str, ActaDetalle], ids: dict[tuple[str, int], str],
) -> dict[str, int]:
    completas = [_votacion_to_row(a, detalles[a.acta_id]) for a in listado if a.acta_id in detalles]
    # Detalle caído en esta corrida: entra igual desde el listado para que la
    # votación aparezca, pero sin pisar una fila que ya exista (tendría la hora
    # y los totales que el listado no trae). La próxima corrida reintenta.
    solo_listado = [_votacion_to_row(a, None) for a in listado if a.acta_id not in detalles]

    # 1) senadores que aparecen en las actas y todavía no están
    minimos: dict[str, dict[str, Any]] = {}
    for d in detalles.values():
        for i, v in enumerate(d.votos):
            eid = ids[(d.acta_id, i)]
            minimos.setdefault(eid, _legislador_desde_voto(v, eid))
    leg_ids = await _asegurar_legisladores(minimos)

    # 2) votaciones (sin `sesion_id`: lo pone `_vincular_sesiones` y no se pisa)
    actualizar = [c for c in completas[0] if c not in ("camara", "external_id")] if completas else []
    vot = await _upsert(
        Votacion, completas, conflicto=["camara", "external_id"], actualizar=actualizar,
        returning=(Votacion.id, Votacion.external_id),
    )
    if solo_listado:
        async with session_scope() as session:
            for i in range(0, len(solo_listado), _BATCH):
                stmt = insert(Votacion).values(solo_listado[i : i + _BATCH])
                await session.execute(stmt.on_conflict_do_nothing(
                    index_elements=["camara", "external_id"]
                ))
    vot_ids = {r.external_id: r.id for r in vot}

    # 3) votos
    votos: list[dict[str, Any]] = []
    for d in detalles.values():
        for i, v in enumerate(d.votos):
            votos.append(_voto_to_row(vot_ids[d.acta_id], leg_ids[ids[(d.acta_id, i)]], v))
    await _upsert(
        Voto, votos, conflicto=["votacion_id", "legislador_id"],
        actualizar=["voto", "bloque", "distrito"],
    )
    return {"votaciones": len(completas) + len(solo_listado), "votos": len(votos)}


@celery_app.task(name="vigia_workers.congreso_senado.ingest_senado_votaciones")
def ingest_senado_votaciones(dry_run: bool = False, anio_desde: int | None = None) -> dict[str, Any]:
    """Actas de votación del Senado con voto nominal.

    Diaria: año en curso y el anterior (una sesión de diciembre puede cargarse en
    enero). Con `anio_desde` hace backfill desde ese año (`ANIO_BACKFILL`=2008
    empata con las sesiones de HCDN): ~2.500 actas y ~180k votos.

    Saltea el detalle de las actas que ya tienen votos guardados, así que la
    corrida diaria baja solo lo nuevo (más las que quedaron sin nominal).
    """
    dry = _dry(dry_run)
    hoy = _hoy()
    desde = anio_desde if anio_desde is not None else hoy.year - 1
    anios = list(range(hoy.year, desde - 1, -1))  # lo nuevo primero

    async def _run() -> dict[str, Any]:
        tot = {"actas_listadas": 0, "detalles_bajados": 0, "votos": 0}
        sin_votos: list[str] = []
        fallidos: list[str] = []
        inexistentes: list[str] = []
        resolucion = {"por_link": 0, "por_indice": 0, "sinteticos": 0}
        sample: list[dict[str, Any]] = []
        existentes = set() if dry else await _actas_con_votos()
        indice: IndiceSenadores | None = None
        async with SenadoActividadClient() as client:
            for anio in anios:
                listado = await client.fetch_actas(None if anio == hoy.year else anio)
                tot["actas_listadas"] += len(listado)
                pendientes = [a.acta_id for a in listado if a.acta_id not in existentes]
                if not pendientes:
                    continue
                bajados, caidos = await client.fetch_detalles(pendientes)
                fallidos.extend(caidos)
                detalles = {k: v for k, v in bajados.items() if v is not None}
                inexistentes.extend(k for k, v in bajados.items() if v is None)
                tot["detalles_bajados"] += len(detalles)
                sin_votos.extend(k for k, d in detalles.items() if not d.votos)

                if indice is None and any(not v.senador_id for d in detalles.values() for v in d.votos):
                    # Solo hace falta para actas con ex senadores (sin link al perfil).
                    indice = IndiceSenadores(
                        [*await client.fetch_senadores_historico(), *await client.fetch_senadores()]
                    )
                ids, st = _resolver_ids(detalles.values(), indice)
                for k, v in st.items():
                    resolucion[k] += v
                tot["votos"] += sum(len(d.votos) for d in detalles.values())

                # Solo se guarda lo pendiente: lo demás ya está cerrado.
                set_pendientes = set(pendientes)
                por_guardar = [a for a in listado if a.acta_id in set_pendientes]
                if dry:
                    for a in por_guardar[: max(0, _DRY_SAMPLE - len(sample))]:
                        r = _votacion_to_row(a, detalles.get(a.acta_id))
                        sample.append({k: _jsonable(r[k]) for k in (
                            "external_id", "fecha", "titulo", "etapa", "resultado",
                            "afirmativos", "negativos", "expedientes", "ordenes_del_dia")})
                    continue
                await _guardar_anio(por_guardar, detalles, ids)

        out: dict[str, Any] = {
            "anios": [desde, hoy.year],
            **tot,
            "sin_votos": sin_votos,
            "fallidos": fallidos,
            "inexistentes": inexistentes,
            "senadores": resolucion,
        }
        if dry:
            out["sample"] = sample
        else:
            out["sesiones_vinculadas"] = await _vincular_sesiones()
        return out

    if dry:
        return {"source": "senado_votaciones", "dry_run": True, **run_async(_run())}

    async def _wrapped() -> dict[str, Any]:
        await ensure_source("senado_votaciones")
        return {"source": "senado_votaciones", **await with_status(["senado_votaciones"], _run)}

    result = run_async(_wrapped())

    # Ninguna de las dos cosas es un corte de la fuente: `warn` deja el motivo
    # visible en /health/sources sin poner la fuente en rojo ni mandar mail.
    motivos: list[str] = []
    if result["sin_votos"]:
        ids = result["sin_votos"]
        motivos.append(
            f"{len(ids)} acta(s) sin filas de voto nominal ({', '.join(ids[:10])}"
            f"{'…' if len(ids) > 10 else ''}) — se reintentan en la próxima corrida"
        )
    if result["fallidos"]:
        ids = result["fallidos"]
        motivos.append(f"{len(ids)} detalle(s) de acta no se pudieron bajar ({', '.join(ids[:10])})")
    if motivos:
        run_async(mark_source_run("senado_votaciones", status="warn", error="; ".join(motivos)[:1000]))
    return result


# ---------------------------------------------------------------------------
# senadores
# ---------------------------------------------------------------------------

@celery_app.task(name="vigia_workers.congreso_senado.ingest_senado_legisladores")
def ingest_senado_legisladores(dry_run: bool = False) -> dict[str, Any]:
    """Senadores en ejercicio (activo) + ex senadores desde 1983 (inactivos).

    Los que salen del listado actual pasan a `activo=false`. Los ex senadores
    salen del export histórico: sin ellos, los votos viejos quedarían colgados
    de altas mínimas sin mandato.
    """
    dry = _dry(dry_run)

    async def _run() -> dict[str, Any]:
        async with SenadoActividadClient() as client:
            actuales = await client.fetch_senadores()
            historico = await client.fetch_senadores_historico()
        ids_actuales = {s.external_id for s in actuales}
        ex = _historico_a_senadores(historico, excluir=ids_actuales)
        rows_act = [_senador_to_row(s, activo=True) for s in actuales]
        rows_ex = [_senador_to_row(s, activo=False) for s in ex]
        out: dict[str, Any] = {"en_ejercicio": len(rows_act), "ex_senadores": len(rows_ex)}
        if dry:
            out["sample"] = [
                {k: _jsonable(r[k]) for k in ("external_id", "nombre", "bloque", "distrito",
                                              "mandato_desde", "mandato_hasta", "activo")}
                for r in rows_act[:3] + rows_ex[:2]
            ]
            return out
        cols = ["nombre", "bloque", "distrito", "mandato_desde", "mandato_hasta", "activo", "raw"]
        await _upsert(Legislador, rows_act, conflicto=["camara", "external_id"],
                      actualizar=cols, extra_set={"updated_at": func.now()})
        # Ex senadores: el histórico no trae bloque, solo partido. Si ya hay un
        # bloque (de un acta) se conserva: es más preciso que el partido.
        await _upsert(
            Legislador, rows_ex, conflicto=["camara", "external_id"],
            actualizar=[c for c in cols if c != "bloque"],
            extra_set=lambda st: {
                "updated_at": func.now(),
                "bloque": func.coalesce(Legislador.__table__.c.bloque, st.excluded.bloque),
            },
        )
        out["desactivados"] = 0
        if len(ids_actuales) >= _MIN_SENADORES:
            async with session_scope() as session:
                res = await session.execute(text(
                    "UPDATE legislador SET activo = false, updated_at = now() "
                    "WHERE camara = :c AND activo AND NOT (external_id = ANY(:ids))"
                ), {"c": _CAMARA, "ids": list(ids_actuales)})
                out["desactivados"] = res.rowcount or 0
        return out

    if dry:
        return {"source": "senado_legisladores", "dry_run": True, **run_async(_run())}

    async def _wrapped() -> dict[str, Any]:
        await ensure_source("senado_legisladores")
        return {"source": "senado_legisladores", **await with_status(["senado_legisladores"], _run)}

    result = run_async(_wrapped())
    if result["en_ejercicio"] < _MIN_SENADORES:
        run_async(mark_source_run(
            "senado_legisladores", status="warn",
            error=(f"el listado de senadores en ejercicio trajo {result['en_ejercicio']} "
                   f"(son 72): no se desactivó a nadie"),
        ))
    return result


# ---------------------------------------------------------------------------
# agenda de comisiones
# ---------------------------------------------------------------------------

def en_receso(d: date) -> bool:
    """Receso del Senado: verano (enero y febrero) y ~3 semanas de invierno en julio.

    Aproximado a propósito: solo decide si una agenda vacía merece un `warn`.
    """
    return d.month in (1, 2) or (d.month == 7 and d.day >= 8)


def agenda_vacia_sospechosa(d: date) -> bool:
    """Una agenda vacía es rara de lunes a jueves fuera de receso.

    El viernes no cuenta: la agenda muestra los próximos días y la de la semana
    que viene suele cargarse recién el lunes.
    """
    return d.weekday() <= 3 and not en_receso(d)


def reuniones_a_dar_de_baja(
    guardadas: Iterable[tuple[str, datetime]],
    scrapeadas: list[dict[str, Any]],
    *,
    ahora: datetime,
) -> list[str]:
    """Reuniones guardadas que la agenda de hoy ya no trae: suspendidas o reprogramadas.

    El `external_id` es un hash de fecha_hora + comisión, así que una reunión que
    cambia de hora deja la fila vieja y suma una nueva; una suspendida desaparece
    de la agenda pero seguiría en la base como si se fuera a hacer. Se da de baja
    una guardada si las tres cosas son ciertas:
    - todavía no pasó (`fecha_hora >= ahora`): el pasado no se toca;
    - su día (hora argentina) es uno de los que trajo la agenda: de los días que
      la página no muestra no sabemos nada;
    - su `external_id` no está entre las scrapeadas.

    Con la agenda vacía no se da de baja nada (para eso está el `warn`).
    """
    if not scrapeadas:
        return []
    dias = {r["fecha_hora"].astimezone(ART).date() for r in scrapeadas}
    vigentes = {r["external_id"] for r in scrapeadas}
    return [
        eid for eid, fh in guardadas
        if fh >= ahora and fh.astimezone(ART).date() in dias and eid not in vigentes
    ]


@celery_app.task(name="vigia_workers.congreso_senado.ingest_senado_agenda")
def ingest_senado_agenda(dry_run: bool = False) -> dict[str, Any]:
    """Agenda de comisiones (y de asesores) de los próximos días.

    Después del upsert da de baja las reuniones suspendidas o reprogramadas
    (`reuniones_a_dar_de_baja`), para que "esta semana" no muestre fantasmas.
    """
    dry = _dry(dry_run)
    hoy = _hoy()

    async def _run() -> dict[str, Any]:
        async with SenadoActividadClient() as client:
            reuniones = await client.fetch_agenda(hoy)
        rows = [_reunion_to_row(r) for r in reuniones]
        out: dict[str, Any] = {
            "reuniones": len(rows),
            "con_expedientes": sum(1 for r in rows if r["expedientes"]),
            "expedientes": sum(len(r["expedientes"]) for r in rows),
        }
        if dry:
            out["sample"] = [
                {k: _jsonable(r[k]) for k in ("fecha_hora", "comision", "sala", "tipo", "expedientes")}
                for r in rows[:_DRY_SAMPLE]
            ]
            return out
        await _upsert(
            ReunionComision, rows, conflicto=["camara", "external_id"],
            actualizar=["fecha_hora", "comision", "sala", "tipo", "temario",
                        "expedientes", "url_citacion", "raw"],
        )
        out["bajas"] = 0
        if rows:
            async with session_scope() as session:
                futuras = (await session.execute(text(
                    "SELECT external_id, fecha_hora FROM reunion_comision "
                    "WHERE camara = :c AND fecha_hora >= now()"
                ), {"c": _CAMARA})).all()
                bajas = reuniones_a_dar_de_baja(
                    [(f[0], f[1]) for f in futuras], rows, ahora=datetime.now(ART)
                )
                if bajas:
                    res = await session.execute(text(
                        "DELETE FROM reunion_comision WHERE camara = :c AND external_id = ANY(:ids)"
                    ), {"c": _CAMARA, "ids": bajas})
                    out["bajas"] = res.rowcount or 0
        return out

    if dry:
        return {"source": "senado_agenda", "dry_run": True, **run_async(_run())}

    async def _wrapped() -> dict[str, Any]:
        await ensure_source("senado_agenda")
        return {"source": "senado_agenda", **await with_status(["senado_agenda"], _run)}

    result = run_async(_wrapped())
    if result["reuniones"] == 0 and agenda_vacia_sospechosa(hoy):
        run_async(mark_source_run(
            "senado_agenda", status="warn",
            error=f"agenda de comisiones vacía el {hoy.isoformat()}, día hábil fuera de receso",
        ))
    return result


# ---------------------------------------------------------------------------
# sesiones
# ---------------------------------------------------------------------------

@celery_app.task(name="vigia_workers.congreso_senado.ingest_senado_sesiones")
def ingest_senado_sesiones(dry_run: bool = False) -> dict[str, Any]:
    """Sesiones del recinto desde 1983 (`busquedaTac`, una sola página).

    Re-upsertea todo a diario: son ~1.800 filas y así se recogen las versiones
    taquigráficas que el Senado sube días después de la sesión.
    """
    dry = _dry(dry_run)

    async def _run() -> dict[str, Any]:
        async with SenadoActividadClient() as client:
            sesiones = await client.fetch_sesiones()
        rows = [_sesion_to_row(s) for s in sesiones]
        out: dict[str, Any] = {
            "sesiones": len(rows),
            "con_taquigrafica": sum(1 for r in rows if r["url_taquigrafica"]),
            "desde": min((r["fecha"] for r in rows), default=None),
            "hasta": max((r["fecha"] for r in rows), default=None),
        }
        if dry:
            out["sample"] = [
                {k: _jsonable(r[k]) for k in ("external_id", "fecha", "tipo", "reunion", "numero_sesion")}
                for r in rows[:_DRY_SAMPLE]
            ]
            return _jsonable(out)
        await _upsert(
            CongresoSesion, rows, conflicto=["camara", "external_id"],
            actualizar=["fecha", "tipo", "reunion", "numero_sesion", "url",
                        "url_taquigrafica", "url_diario", "raw"],
        )
        out["votaciones_vinculadas"] = await _vincular_sesiones()
        return _jsonable(out)

    if dry:
        return {"source": "senado_sesiones", "dry_run": True, **run_async(_run())}

    async def _wrapped() -> dict[str, Any]:
        await ensure_source("senado_sesiones")
        return {"source": "senado_sesiones", **await with_status(["senado_sesiones"], _run)}

    return run_async(_wrapped())
