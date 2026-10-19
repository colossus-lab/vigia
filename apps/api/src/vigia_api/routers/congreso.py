"""Congreso: votaciones, sesiones, agenda de comisiones y legisladores.

Contrato: `docs/congreso-api.md` (lo consume la sección web en paralelo: no
cambiar un shape sin cambiarlo ahí primero). Endpoints públicos como el resto
de los datos; el gating de la sección lo hace el web.

Lo que pasa en el Congreso vive en tablas propias (migración 0012) y se cruza
con los proyectos (`norma`) por expediente canónico: `norma.expedientes &&
x.expedientes`, GIN en las dos puntas. Los proyectos de una página entera
salen de UNA consulta (`_proyectos_para`), nunca uno por ítem.

Las cuentas (desglose por bloque, presentismo, alineamiento) son helpers puros
para poder testear los bordes sin base.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import date as Date
from datetime import datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from vigia_api.core.cache import cached
from vigia_api.core.db import get_sessionmaker
from vigia_shared.expedientes import normalizar_expediente
from vigia_shared.models import (
    AsuntoTratado,
    CongresoSesion,
    Legislador,
    Norma,
    ReunionComision,
    Votacion,
    Voto,
)

router = APIRouter(prefix="/congreso", tags=["congreso"])

# Argentina no tiene horario de verano desde 2009: un offset fijo alcanza y no
# depende de que el host tenga la base de zonas horarias (Windows no la trae).
ART = timezone(timedelta(hours=-3))

_CAMARA = "^[SD]$"
_MAX_PROYECTOS = 10        # por ítem (contrato)
_RESUMEN_TTL = 300.0
_DIAS_ESTADISTICAS = 365
_MAX_VOTOS_RECIENTES = 20
_MAX_CONGRESO_NORMA = 20   # por lista, en GET /normas/{id}

# Fuente de los proyectos de cada cámara, para `proyectos_30d`.
_FUENTE_PROYECTOS = {"S": "senado_proyectos", "D": "hcdn_proyectos"}


# ── modelos ──────────────────────────────────────────────────────────────────


class ProyectoRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str
    numero: str | None
    estado: str | None
    fecha_publicacion: Date | None


class CamaraResumen(BaseModel):
    reuniones_proximas: int
    # None = la cámara no tiene fuente de voto nominal (Diputados: reCAPTCHA).
    # No es un cero: el web muestra "sin datos".
    votaciones_30d: int | None
    sesiones_30d: int
    proyectos_30d: int
    ultima_sesion: Date | None


class Resumen(BaseModel):
    S: CamaraResumen
    D: CamaraResumen
    actualizado: datetime


class ReunionItem(BaseModel):
    id: int
    camara: str
    fecha_hora: datetime
    comision: str
    sala: str | None
    tipo: str | None
    temario: str | None
    expedientes: list[str]
    url_citacion: str | None
    proyectos: list[ProyectoRef] = []


class ReunionPage(BaseModel):
    items: list[ReunionItem]
    total: int
    limit: int
    offset: int


class VotacionItem(BaseModel):
    id: int
    camara: str
    fecha: datetime
    numero_acta: str | None
    titulo: str
    etapa: str | None
    resultado: str | None
    mayoria: str | None
    afirmativos: int | None
    negativos: int | None
    abstenciones: int | None
    ausentes: int | None
    expedientes: list[str]
    ordenes_del_dia: list[str]
    sesion_id: int | None
    url: str | None
    url_pdf: str | None
    video_url: str | None


class VotacionPage(BaseModel):
    items: list[VotacionItem]
    total: int
    limit: int
    offset: int


class SesionRef(BaseModel):
    id: int
    fecha: Date
    tipo: str | None


class BloqueVotos(BaseModel):
    bloque: str | None
    afirmativo: int
    negativo: int
    abstencion: int
    ausente: int
    otro: int
    total: int


class VotoItem(BaseModel):
    legislador_id: int
    nombre: str
    bloque: str | None
    distrito: str | None
    voto: str


class VotacionDetail(VotacionItem):
    proyectos: list[ProyectoRef]
    sesion: SesionRef | None
    por_bloque: list[BloqueVotos]
    votos: list[VotoItem]


class SesionItem(BaseModel):
    id: int
    camara: str
    fecha: Date
    tipo: str | None
    periodo: int | None
    reunion: int | None
    numero_sesion: int | None
    url: str | None
    url_taquigrafica: str | None
    url_diario: str | None
    votaciones: int
    asuntos: int


class SesionPage(BaseModel):
    items: list[SesionItem]
    total: int
    limit: int
    offset: int


class AsuntoItem(BaseModel):
    id: int
    clave: str
    orden_del_dia: str | None
    tipo: str | None
    sumario: str | None
    resultado: str | None
    expedientes: list[str]
    proyectos: list[ProyectoRef] = []


class SesionDetail(SesionItem):
    # Mismo nombre que los conteos del ítem, pero acá son las listas.
    votaciones: list[VotacionItem]  # type: ignore[assignment]
    asuntos: list[AsuntoItem]  # type: ignore[assignment]


class LegisladorItem(BaseModel):
    id: int
    camara: str
    nombre: str
    bloque: str | None
    distrito: str | None
    mandato_desde: Date | None
    mandato_hasta: Date | None
    activo: bool


class LegisladorPage(BaseModel):
    items: list[LegisladorItem]
    total: int
    limit: int
    offset: int


class Estadisticas(BaseModel):
    votaciones: int
    presentes: int
    presentismo: float | None
    alineamiento_bloque: float | None


class VotoReciente(BaseModel):
    votacion_id: int
    fecha: datetime
    titulo: str
    voto: str
    resultado: str | None


class LegisladorDetail(LegisladorItem):
    estadisticas: Estadisticas | None
    votos_recientes: list[VotoReciente]


class ActividadItem(BaseModel):
    tipo: str  # votacion | sesion | reunion
    id: int
    camara: str
    fecha: datetime
    titulo: str
    detalle: str | None


class Actividad(BaseModel):
    items: list[ActividadItem]


class AsuntoConFecha(AsuntoItem):
    camara: str
    sesion_id: int
    fecha: Date


class CongresoDeNorma(BaseModel):
    votaciones: list[VotacionItem]
    asuntos: list[AsuntoConFecha]
    reuniones: list[ReunionItem]


# ── helpers puros ────────────────────────────────────────────────────────────

_COLUMNAS_BLOQUE = ("afirmativo", "negativo", "abstencion", "ausente")


def desglose_por_bloque(votos: Iterable[tuple[str | None, str]]) -> list[dict[str, Any]]:
    """Cuenta votos por bloque. `votos` = pares (bloque, voto).

    `presidente` (quien preside no vota) y `otro` (celda vacía en el acta) van
    juntos en `otro`: el contrato no tiene columna para el presidente y en la
    práctica es una sola persona por votación. Orden: `total` DESC y, a igual
    total, nombre de bloque, para que la salida no dependa del orden de llegada.
    """
    por: dict[str | None, Counter] = {}
    for bloque, voto in votos:
        c = por.setdefault(bloque, Counter())
        c[voto if voto in _COLUMNAS_BLOQUE else "otro"] += 1
    filas = []
    for bloque, c in por.items():
        fila: dict[str, Any] = {"bloque": bloque}
        for col in (*_COLUMNAS_BLOQUE, "otro"):
            fila[col] = c[col]
        fila["total"] = sum(c.values())
        filas.append(fila)
    filas.sort(key=lambda f: (-f["total"], f["bloque"] is None, f["bloque"] or ""))
    return filas


def presentismo(votaciones: int, ausentes: int) -> tuple[int, float | None]:
    """(presentes, presentismo). Sin votaciones no hay tasa: None, no 0."""
    presentes = votaciones - ausentes
    if votaciones <= 0:
        return 0, None
    return presentes, round(presentes / votaciones, 3)


def alineamiento_bloque(filas: Iterable[tuple[str, int, int]]) -> float | None:
    """Fracción de votaciones en que el legislador votó como la mayoría de su bloque.

    `filas` = (voto propio, afirmativos del bloque, negativos del bloque), con
    los conteos del bloque **incluyéndolo a él**, una fila por votación. Solo
    cuentan los votos afirmativo/negativo. Se descartan:

    - las votaciones donde el bloque empató: no hay mayoría con la que alinear;
    - las votaciones donde fue el único de su bloque en votar sí/no
      (monobloques): alinearse con uno mismo daría 100% y no dice nada.

    Sin ninguna votación que cuente devuelve None.
    """
    consideradas = alineadas = 0
    for voto, af, neg in filas:
        if voto not in ("afirmativo", "negativo"):
            continue
        if af + neg <= 1 or af == neg:
            continue
        consideradas += 1
        mayoria = "afirmativo" if af > neg else "negativo"
        alineadas += voto == mayoria
    if not consideradas:
        return None
    return round(alineadas / consideradas, 3)


def detalle_votacion(resultado: str | None, afirmativos: int | None, negativos: int | None) -> str | None:
    """`afirmativo 42-30` para el timeline del hub."""
    partes = []
    if resultado:
        partes.append(resultado)
    if afirmativos is not None and negativos is not None:
        partes.append(f"{afirmativos}-{negativos}")
    return " ".join(partes) or None


def asignar_proyectos(
    listas: Sequence[Sequence[str]], proyectos: Sequence[tuple[ProyectoRef, Sequence[str]]]
) -> list[list[ProyectoRef]]:
    """Reparte los proyectos traídos en una consulta entre los ítems de la página.

    `proyectos` = (proyecto, sus expedientes), ya ordenados. A cada ítem le
    tocan los que comparten algún expediente con él, hasta `_MAX_PROYECTOS`.
    """
    salida: list[list[ProyectoRef]] = []
    for exps in listas:
        mios = set(exps)
        out: list[ProyectoRef] = []
        if mios:
            for p, p_exps in proyectos:
                if mios.intersection(p_exps):
                    out.append(p)
                    if len(out) >= _MAX_PROYECTOS:
                        break
        salida.append(out)
    return salida


def _art(dt: datetime) -> datetime:
    return dt.astimezone(ART)


def _inicio_dia(d: Date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=ART)


def _hoy() -> Date:
    return datetime.now(ART).date()


# ── consultas compartidas ────────────────────────────────────────────────────


async def _proyectos_para(
    session: AsyncSession, listas: Sequence[Sequence[str]]
) -> list[list[ProyectoRef]]:
    todos = sorted({e for exps in listas for e in exps})
    if not todos:
        return [[] for _ in listas]
    rows = (
        await session.execute(
            select(
                Norma.id, Norma.titulo, Norma.numero, Norma.estado,
                Norma.fecha_publicacion, Norma.expedientes,
            )
            .where(Norma.tipo == "PROYECTO", Norma.expedientes.overlap(todos))
            .order_by(Norma.fecha_publicacion.desc().nullslast(), Norma.id.desc())
            # Tope defensivo: una página no puede pedir más que esto.
            .limit(_MAX_PROYECTOS * max(len(listas), 1) * 4)
        )
    ).all()
    proyectos = [
        (
            ProyectoRef(
                id=r.id, titulo=r.titulo, numero=r.numero,
                estado=r.estado, fecha_publicacion=r.fecha_publicacion,
            ),
            r.expedientes or [],
        )
        for r in rows
    ]
    return asignar_proyectos(listas, proyectos)


def _votacion_item(v: Votacion) -> VotacionItem:
    return VotacionItem(
        id=v.id, camara=v.camara, fecha=_art(v.fecha), numero_acta=v.numero_acta,
        titulo=v.titulo, etapa=v.etapa, resultado=v.resultado, mayoria=v.mayoria,
        afirmativos=v.afirmativos, negativos=v.negativos, abstenciones=v.abstenciones,
        ausentes=v.ausentes, expedientes=list(v.expedientes or []),
        ordenes_del_dia=list(v.ordenes_del_dia or []), sesion_id=v.sesion_id,
        url=v.url, url_pdf=v.url_pdf, video_url=v.video_url,
    )


def _reunion_item(r: ReunionComision, proyectos: list[ProyectoRef]) -> ReunionItem:
    return ReunionItem(
        id=r.id, camara=r.camara, fecha_hora=_art(r.fecha_hora), comision=r.comision,
        sala=r.sala, tipo=r.tipo, temario=r.temario, expedientes=list(r.expedientes or []),
        url_citacion=r.url_citacion, proyectos=proyectos,
    )


def _asunto_kwargs(a: AsuntoTratado, proyectos: list[ProyectoRef]) -> dict[str, Any]:
    return dict(
        id=a.id, clave=a.clave, orden_del_dia=a.orden_del_dia, tipo=a.tipo,
        sumario=a.sumario, resultado=a.resultado, expedientes=list(a.expedientes or []),
        proyectos=proyectos,
    )


def _legislador_kwargs(l: Legislador) -> dict[str, Any]:
    return dict(
        id=l.id, camara=l.camara, nombre=l.nombre, bloque=l.bloque, distrito=l.distrito,
        mandato_desde=l.mandato_desde, mandato_hasta=l.mandato_hasta, activo=l.activo,
    )


def _no_encontrado() -> HTTPException:
    return HTTPException(status_code=404, detail="no_encontrado")


def _fts(q: str):
    return text("search_vector @@ plainto_tsquery('spanish', :q)").bindparams(q=q)


# Columnas de los conteos de una sesión: subconsultas correlacionadas, que van
# por ix_votacion_sesion y por el índice único (sesion_id, clave) de asunto.
_N_VOTACIONES = (
    select(func.count())
    .select_from(Votacion)
    .where(Votacion.sesion_id == CongresoSesion.id)
    .correlate(CongresoSesion)
    .scalar_subquery()
)
_N_ASUNTOS = (
    select(func.count())
    .select_from(AsuntoTratado)
    .where(AsuntoTratado.sesion_id == CongresoSesion.id)
    .correlate(CongresoSesion)
    .scalar_subquery()
)


def _sesion_kwargs(s: CongresoSesion, n_vot: int, n_asu: int) -> dict[str, Any]:
    return dict(
        id=s.id, camara=s.camara, fecha=s.fecha, tipo=s.tipo, periodo=s.periodo,
        reunion=s.reunion, numero_sesion=s.numero_sesion, url=s.url,
        url_taquigrafica=s.url_taquigrafica, url_diario=s.url_diario,
        votaciones=int(n_vot or 0), asuntos=int(n_asu or 0),
    )


# ── /resumen ─────────────────────────────────────────────────────────────────


@router.get("/resumen", response_model=Resumen)
async def resumen() -> Resumen:
    """KPIs del hub. Cacheado: la ingesta del Congreso es diaria."""
    return await cached("congreso:resumen", _RESUMEN_TTL, _resumen_uncached)


async def _resumen_uncached() -> Resumen:
    Session = get_sessionmaker()
    async with Session() as session:
        rows = (
            await session.execute(
                text(
                    """
                    WITH c(camara, fuente) AS (VALUES ('S', :fs), ('D', :fd))
                    SELECT c.camara,
                      (SELECT COUNT(*) FROM reunion_comision r
                        WHERE r.camara = c.camara AND r.fecha_hora >= now()) AS reuniones_proximas,
                      (SELECT COUNT(*) FROM votacion v
                        WHERE v.camara = c.camara AND v.fecha >= now() - interval '30 days') AS votaciones_30d,
                      EXISTS (SELECT 1 FROM votacion v WHERE v.camara = c.camara) AS hay_votaciones,
                      (SELECT COUNT(*) FROM congreso_sesion s
                        WHERE s.camara = c.camara AND s.fecha >= current_date - 30
                          AND s.fecha <= current_date) AS sesiones_30d,
                      (SELECT COUNT(*) FROM norma n
                        WHERE n.tipo = 'PROYECTO'
                          AND n.fecha_publicacion >= current_date - 30
                          AND n.source_id = (SELECT id FROM source_catalog WHERE code = c.fuente)
                      ) AS proyectos_30d,
                      (SELECT MAX(s.fecha) FROM congreso_sesion s
                        WHERE s.camara = c.camara AND s.fecha <= current_date) AS ultima_sesion
                    FROM c
                    """
                ),
                {"fs": _FUENTE_PROYECTOS["S"], "fd": _FUENTE_PROYECTOS["D"]},
            )
        ).all()
    por = {
        r.camara: CamaraResumen(
            reuniones_proximas=int(r.reuniones_proximas or 0),
            votaciones_30d=int(r.votaciones_30d or 0) if r.hay_votaciones else None,
            sesiones_30d=int(r.sesiones_30d or 0),
            proyectos_30d=int(r.proyectos_30d or 0),
            ultima_sesion=r.ultima_sesion,
        )
        for r in rows
    }
    return Resumen(S=por["S"], D=por["D"], actualizado=datetime.now(timezone.utc))


# ── /agenda ──────────────────────────────────────────────────────────────────


@router.get("/agenda", response_model=ReunionPage)
async def agenda(
    camara: str | None = Query(None, pattern=_CAMARA),
    desde: Date | None = Query(None, description="default: hoy"),
    hasta: Date | None = Query(None, description="default: desde + 7 días (inclusive)"),
    comision: str | None = Query(None, description="ILIKE sobre el nombre de la comisión"),
    q: str | None = Query(None, description="FTS sobre comisión y temario"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
) -> ReunionPage:
    desde = desde or _hoy()
    hasta = hasta or desde + timedelta(days=7)
    filters = [
        ReunionComision.fecha_hora >= _inicio_dia(desde),
        ReunionComision.fecha_hora < _inicio_dia(hasta + timedelta(days=1)),
    ]
    if camara:
        filters.append(ReunionComision.camara == camara)
    if comision:
        filters.append(ReunionComision.comision.ilike(f"%{comision}%"))
    if q:
        filters.append(_fts(q))

    Session = get_sessionmaker()
    async with Session() as session:
        total = (
            await session.execute(
                select(func.count()).select_from(ReunionComision).where(*filters)
            )
        ).scalar_one()
        rows = (
            await session.execute(
                select(ReunionComision)
                .where(*filters)
                .order_by(ReunionComision.fecha_hora.asc(), ReunionComision.id.asc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        proyectos = await _proyectos_para(session, [r.expedientes or [] for r in rows])

    return ReunionPage(
        items=[_reunion_item(r, p) for r, p in zip(rows, proyectos)],
        total=int(total or 0), limit=limit, offset=offset,
    )


# ── /votaciones ──────────────────────────────────────────────────────────────


@router.get("/votaciones", response_model=VotacionPage)
async def list_votaciones(
    camara: str | None = Query(None, pattern=_CAMARA),
    q: str | None = Query(None, description="FTS sobre el título"),
    desde: Date | None = Query(None),
    hasta: Date | None = Query(None, description="inclusive"),
    resultado: str | None = Query(None, description="afirmativo | negativo | ..."),
    expediente: str | None = Query(None, description="cualquier forma: se normaliza"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
) -> VotacionPage:
    filters = []
    if camara:
        filters.append(Votacion.camara == camara)
    if q:
        filters.append(_fts(q))
    if desde:
        filters.append(Votacion.fecha >= _inicio_dia(desde))
    if hasta:
        filters.append(Votacion.fecha < _inicio_dia(hasta + timedelta(days=1)))
    if resultado:
        filters.append(func.lower(Votacion.resultado) == resultado.lower())
    if expediente:
        canon = normalizar_expediente(expediente)
        if canon is None:
            # Igual que el cruce: una forma que no normaliza no encuentra nada.
            return VotacionPage(items=[], total=0, limit=limit, offset=offset)
        filters.append(Votacion.expedientes.contains([canon]))

    Session = get_sessionmaker()
    async with Session() as session:
        total = (
            await session.execute(select(func.count()).select_from(Votacion).where(*filters))
        ).scalar_one()
        rows = (
            await session.execute(
                select(Votacion)
                .where(*filters)
                .order_by(Votacion.fecha.desc(), Votacion.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()

    return VotacionPage(
        items=[_votacion_item(v) for v in rows], total=int(total or 0), limit=limit, offset=offset
    )


@router.get("/votaciones/{votacion_id}", response_model=VotacionDetail)
async def get_votacion(votacion_id: int) -> VotacionDetail:
    Session = get_sessionmaker()
    async with Session() as session:
        v = await session.get(Votacion, votacion_id)
        if v is None:
            raise _no_encontrado()
        sesion = await session.get(CongresoSesion, v.sesion_id) if v.sesion_id else None
        votos = (
            await session.execute(
                select(Voto.legislador_id, Legislador.nombre, Voto.bloque, Voto.distrito, Voto.voto)
                .join(Legislador, Legislador.id == Voto.legislador_id)
                .where(Voto.votacion_id == votacion_id)
                .order_by(Voto.bloque.asc().nullslast(), Legislador.nombre.asc())
            )
        ).all()
        (proyectos,) = await _proyectos_para(session, [v.expedientes or []])

    return VotacionDetail(
        **_votacion_item(v).model_dump(),
        proyectos=proyectos,
        sesion=SesionRef(id=sesion.id, fecha=sesion.fecha, tipo=sesion.tipo) if sesion else None,
        por_bloque=[BloqueVotos(**f) for f in desglose_por_bloque((r.bloque, r.voto) for r in votos)],
        votos=[
            VotoItem(
                legislador_id=r.legislador_id, nombre=r.nombre, bloque=r.bloque,
                distrito=r.distrito, voto=r.voto,
            )
            for r in votos
        ],
    )


# ── /sesiones ────────────────────────────────────────────────────────────────


@router.get("/sesiones", response_model=SesionPage)
async def list_sesiones(
    camara: str | None = Query(None, pattern=_CAMARA),
    desde: Date | None = Query(None),
    hasta: Date | None = Query(None, description="inclusive"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
) -> SesionPage:
    filters = []
    if camara:
        filters.append(CongresoSesion.camara == camara)
    if desde:
        filters.append(CongresoSesion.fecha >= desde)
    if hasta:
        filters.append(CongresoSesion.fecha <= hasta)

    Session = get_sessionmaker()
    async with Session() as session:
        total = (
            await session.execute(select(func.count()).select_from(CongresoSesion).where(*filters))
        ).scalar_one()
        rows = (
            await session.execute(
                select(CongresoSesion, _N_VOTACIONES, _N_ASUNTOS)
                .where(*filters)
                .order_by(CongresoSesion.fecha.desc(), CongresoSesion.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()

    return SesionPage(
        items=[SesionItem(**_sesion_kwargs(s, nv, na)) for s, nv, na in rows],
        total=int(total or 0), limit=limit, offset=offset,
    )


@router.get("/sesiones/{sesion_id}", response_model=SesionDetail)
async def get_sesion(sesion_id: int) -> SesionDetail:
    Session = get_sessionmaker()
    async with Session() as session:
        s = await session.get(CongresoSesion, sesion_id)
        if s is None:
            raise _no_encontrado()
        votaciones = (
            await session.execute(
                select(Votacion)
                .where(Votacion.sesion_id == sesion_id)
                .order_by(Votacion.fecha.asc(), Votacion.id.asc())
            )
        ).scalars().all()
        # El orden de inserción es el del boletín: cada corrida reemplaza los
        # asuntos de la sesión enteros, en el orden en que aparecen.
        asuntos = (
            await session.execute(
                select(AsuntoTratado)
                .where(AsuntoTratado.sesion_id == sesion_id)
                .order_by(AsuntoTratado.id.asc())
            )
        ).scalars().all()
        proyectos = await _proyectos_para(session, [a.expedientes or [] for a in asuntos])

    base = _sesion_kwargs(s, 0, 0)
    base.update(
        votaciones=[_votacion_item(v) for v in votaciones],
        asuntos=[AsuntoItem(**_asunto_kwargs(a, p)) for a, p in zip(asuntos, proyectos)],
    )
    return SesionDetail(**base)


# ── /legisladores ────────────────────────────────────────────────────────────


@router.get("/legisladores", response_model=LegisladorPage)
async def list_legisladores(
    camara: str | None = Query(None, pattern=_CAMARA),
    bloque: str | None = Query(None, description="exacto"),
    distrito: str | None = Query(None, description="exacto"),
    q: str | None = Query(None, description="ILIKE sobre el nombre, sin acentos"),
    activo: bool = Query(True),
    limit: int = Query(20, ge=1, le=300),
    offset: int = Query(0, ge=0, le=100000),
) -> LegisladorPage:
    filters = [Legislador.activo.is_(activo)]
    if camara:
        filters.append(Legislador.camara == camara)
    if bloque:
        filters.append(Legislador.bloque == bloque)
    if distrito:
        filters.append(Legislador.distrito == distrito)
    if q:
        # El Senado publica "MAYANS, JOSÉ MIGUEL ÁNGEL": sin unaccent, "jose"
        # no lo encuentra.
        filters.append(func.unaccent(Legislador.nombre).ilike(func.unaccent(f"%{q}%")))

    Session = get_sessionmaker()
    async with Session() as session:
        total = (
            await session.execute(select(func.count()).select_from(Legislador).where(*filters))
        ).scalar_one()
        rows = (
            await session.execute(
                select(Legislador)
                .where(*filters)
                .order_by(Legislador.nombre.asc(), Legislador.id.asc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()

    return LegisladorPage(
        items=[LegisladorItem(**_legislador_kwargs(l)) for l in rows],
        total=int(total or 0), limit=limit, offset=offset,
    )


@router.get("/legisladores/{legislador_id}", response_model=LegisladorDetail)
async def get_legislador(legislador_id: int) -> LegisladorDetail:
    Session = get_sessionmaker()
    async with Session() as session:
        l = await session.get(Legislador, legislador_id)
        if l is None:
            raise _no_encontrado()
        # Sin fuente de voto nominal en la cámara (Diputados), las estadísticas
        # no son cero: no existen.
        hay_fuente = (
            await session.execute(
                select(select(Votacion.id).where(Votacion.camara == l.camara).exists())
            )
        ).scalar_one()
        estadisticas = None
        recientes: Sequence[Any] = []
        if hay_fuente:
            desde = datetime.now(timezone.utc) - timedelta(days=_DIAS_ESTADISTICAS)
            tot = (
                await session.execute(
                    select(
                        func.count(),
                        func.count().filter(Voto.voto == "ausente"),
                    )
                    .select_from(Voto)
                    .join(Votacion, Votacion.id == Voto.votacion_id)
                    .where(Voto.legislador_id == legislador_id, Votacion.fecha >= desde)
                )
            ).one()
            # Por cada votación en que votó sí/no: su voto y cómo votó su bloque
            # (él incluido). El bloque es el del acta, no el de hoy.
            alineacion = (
                await session.execute(
                    text(
                        """
                        SELECT v.voto,
                               COUNT(*) FILTER (WHERE o.voto = 'afirmativo') AS af,
                               COUNT(*) FILTER (WHERE o.voto = 'negativo') AS neg
                        FROM voto v
                        JOIN votacion vt ON vt.id = v.votacion_id
                        JOIN voto o ON o.votacion_id = v.votacion_id AND o.bloque = v.bloque
                        WHERE v.legislador_id = :id AND vt.fecha >= :desde
                          AND v.voto IN ('afirmativo', 'negativo')
                        GROUP BY v.votacion_id, v.voto
                        """
                    ),
                    {"id": legislador_id, "desde": desde},
                )
            ).all()
            n, ausentes = int(tot[0] or 0), int(tot[1] or 0)
            presentes, tasa = presentismo(n, ausentes)
            estadisticas = Estadisticas(
                votaciones=n, presentes=presentes, presentismo=tasa,
                alineamiento_bloque=alineamiento_bloque(
                    (r.voto, int(r.af), int(r.neg)) for r in alineacion
                ),
            )
            recientes = (
                await session.execute(
                    select(Votacion.id, Votacion.fecha, Votacion.titulo, Voto.voto, Votacion.resultado)
                    .join(Voto, Voto.votacion_id == Votacion.id)
                    .where(Voto.legislador_id == legislador_id)
                    .order_by(Votacion.fecha.desc(), Votacion.id.desc())
                    .limit(_MAX_VOTOS_RECIENTES)
                )
            ).all()

    return LegisladorDetail(
        **_legislador_kwargs(l),
        estadisticas=estadisticas,
        votos_recientes=[
            VotoReciente(
                votacion_id=r.id, fecha=_art(r.fecha), titulo=r.titulo,
                voto=r.voto, resultado=r.resultado,
            )
            for r in recientes
        ],
    )


# ── /actividad ───────────────────────────────────────────────────────────────


@router.get("/actividad", response_model=Actividad)
async def actividad(
    camara: str | None = Query(None, pattern=_CAMARA),
    desde: Date | None = Query(None, description="default: hoy − 14 días"),
    limit: int = Query(30, ge=1, le=100),
) -> Actividad:
    """Timeline del hub: votaciones, sesiones y reuniones ya ocurridas.

    Las sesiones solo tienen fecha: van a las 00:00 de ese día (ART) para que
    `fecha` sea siempre un datetime y el orden sea uno solo.
    """
    desde = desde or _hoy() - timedelta(days=14)
    t0 = _inicio_dia(desde)
    ahora = datetime.now(timezone.utc)

    def _cam(col):
        return [col == camara] if camara else []

    Session = get_sessionmaker()
    async with Session() as session:
        # Cada fuente trae a lo sumo `limit`: el merge no necesita más.
        votaciones = (
            await session.execute(
                select(Votacion)
                .where(Votacion.fecha >= t0, Votacion.fecha <= ahora, *_cam(Votacion.camara))
                .order_by(Votacion.fecha.desc(), Votacion.id.desc())
                .limit(limit)
            )
        ).scalars().all()
        sesiones = (
            await session.execute(
                select(CongresoSesion, _N_VOTACIONES, _N_ASUNTOS)
                .where(
                    CongresoSesion.fecha >= desde,
                    CongresoSesion.fecha <= _hoy(),
                    *_cam(CongresoSesion.camara),
                )
                .order_by(CongresoSesion.fecha.desc(), CongresoSesion.id.desc())
                .limit(limit)
            )
        ).all()
        reuniones = (
            await session.execute(
                select(ReunionComision)
                .where(
                    ReunionComision.fecha_hora >= t0,
                    ReunionComision.fecha_hora <= ahora,
                    *_cam(ReunionComision.camara),
                )
                .order_by(ReunionComision.fecha_hora.desc(), ReunionComision.id.desc())
                .limit(limit)
            )
        ).scalars().all()

    items = [
        ActividadItem(
            tipo="votacion", id=v.id, camara=v.camara, fecha=_art(v.fecha), titulo=v.titulo,
            detalle=detalle_votacion(v.resultado, v.afirmativos, v.negativos),
        )
        for v in votaciones
    ]
    items += [
        ActividadItem(
            tipo="sesion", id=s.id, camara=s.camara, fecha=_inicio_dia(s.fecha),
            titulo=s.tipo or "Sesión", detalle=_detalle_sesion(int(nv or 0), int(na or 0)),
        )
        for s, nv, na in sesiones
    ]
    items += [
        ActividadItem(
            tipo="reunion", id=r.id, camara=r.camara, fecha=_art(r.fecha_hora),
            titulo=r.comision, detalle=r.tipo,
        )
        for r in reuniones
    ]
    items.sort(key=lambda i: (i.fecha, i.id), reverse=True)
    return Actividad(items=items[:limit])


def _detalle_sesion(votaciones: int, asuntos: int) -> str | None:
    partes = []
    if votaciones:
        partes.append(f"{votaciones} votaci{'ón' if votaciones == 1 else 'ones'}")
    if asuntos:
        partes.append(f"{asuntos} asunto{'' if asuntos == 1 else 's'} tratado{'' if asuntos == 1 else 's'}")
    return " · ".join(partes) or None


# ── cruce para GET /normas/{id} ──────────────────────────────────────────────


async def congreso_de_norma(
    session: AsyncSession, expedientes: Sequence[str] | None
) -> dict[str, Any] | None:
    """Lo que pasó en el Congreso con los expedientes de una norma, o None.

    Devuelve un dict ya serializable (JSON mode) porque `NormaDetail` vive en
    `vigia_shared` y no conoce los modelos de este router.
    """
    exps = list(expedientes or [])
    if not exps:
        return None
    votaciones = (
        await session.execute(
            select(Votacion)
            .where(Votacion.expedientes.overlap(exps))
            .order_by(Votacion.fecha.desc(), Votacion.id.desc())
            .limit(_MAX_CONGRESO_NORMA)
        )
    ).scalars().all()
    asuntos = (
        await session.execute(
            select(AsuntoTratado, CongresoSesion.fecha)
            .join(CongresoSesion, CongresoSesion.id == AsuntoTratado.sesion_id)
            .where(AsuntoTratado.expedientes.overlap(exps))
            .order_by(CongresoSesion.fecha.desc(), AsuntoTratado.id.desc())
            .limit(_MAX_CONGRESO_NORMA)
        )
    ).all()
    # Las próximas primero (la más cercana arriba) y después las pasadas, de
    # la más reciente para atrás.
    ahora = datetime.now(timezone.utc)
    futura = ReunionComision.fecha_hora >= ahora
    reuniones = (
        await session.execute(
            select(ReunionComision)
            .where(ReunionComision.expedientes.overlap(exps))
            .order_by(
                futura.desc(),
                func.abs(func.extract("epoch", ReunionComision.fecha_hora - ahora)),
                ReunionComision.id.desc(),
            )
            .limit(_MAX_CONGRESO_NORMA)
        )
    ).scalars().all()
    if not (votaciones or asuntos or reuniones):
        return None

    listas = [a.expedientes or [] for a, _ in asuntos] + [r.expedientes or [] for r in reuniones]
    proyectos = await _proyectos_para(session, listas)
    p_asuntos, p_reuniones = proyectos[: len(asuntos)], proyectos[len(asuntos):]
    return CongresoDeNorma(
        votaciones=[_votacion_item(v) for v in votaciones],
        asuntos=[
            AsuntoConFecha(**_asunto_kwargs(a, p), camara=a.camara, sesion_id=a.sesion_id, fecha=f)
            for (a, f), p in zip(asuntos, p_asuntos)
        ],
        reuniones=[_reunion_item(r, p) for r, p in zip(reuniones, p_reuniones)],
    ).model_dump(mode="json")
