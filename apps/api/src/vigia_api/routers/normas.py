"""Feed de normas + detalle. Lee de Postgres (poblado por el worker InfoLEG)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from vigia_api.core.cache import cached
from vigia_api.core.db import get_sessionmaker
from vigia_shared.models import DnuTracking, Norma, SourceCatalog
from vigia_shared.relevancia import PESO_TIPO, es_tramite
from vigia_shared.schemas import NormaDetail, NormaListItem, NormaPage

router = APIRouter(prefix="/normas", tags=["normas"])

# Topes por edición (el cliente muestra lo que llega; el resto queda contado).
_MAX_DESTACADOS = 30
_MAX_TRAMITE = 80

# TTL del COUNT del feed. La ingesta es diaria: el total puede atrasarse unos
# minutos sin que se note en un contador de medio millón.
_COUNT_TTL = 300.0


def _apply_source(filters: list, source: str | None) -> None:
    """Filtra por código(s) de fuente (lista separada por coma) vía source_catalog.

    Habilita la sección "Boletines Oficiales": Nacional→bora_primera,infoleg;
    PBA→bopba; CABA→bocaba.
    """
    if not source:
        return
    codes = [c.strip() for c in source.split(",") if c.strip()]
    if codes:
        filters.append(
            Norma.source_id.in_(select(SourceCatalog.id).where(SourceCatalog.code.in_(codes)))
        )


@router.get("/ediciones")
async def ediciones(
    dias: int = Query(7, ge=1, le=31, description="cuántas ediciones (días con normas) traer"),
    offset_dias: int = Query(0, ge=0, le=365, description="paginación: saltear N ediciones"),
    tipo: str | None = Query(None),
    sector: str | None = Query(None),
    emisor: str | None = Query(None, description="organismo canónico: ARCA|CNV|BCRA|…"),
    source: str | None = Query(
        None, description="códigos de fuente separados por coma: bora_primera,infoleg|bocaba|bopba"
    ),
) -> dict:
    """El feed como diario: una edición por día, con jerarquía editorial.

    Cada edición separa `destacados` (DNU, leyes, decretos de alcance general,
    normativa regulatoria) de `tramite` (edictos, designaciones, beneplácitos),
    que el cliente colapsa en una línea. Orden: peso editorial del tipo.
    """
    Session = get_sessionmaker()
    filters = []
    if tipo:
        filters.append(Norma.tipo == tipo)
    if sector:
        filters.append(Norma.sector == sector)
    if emisor:
        filters.append(Norma.emisor == emisor)
    _apply_source(filters, source)

    async with Session() as session:
        fechas = (
            await session.execute(
                select(Norma.fecha_publicacion)
                .where(Norma.fecha_publicacion.isnot(None), *filters)
                .group_by(Norma.fecha_publicacion)
                .order_by(Norma.fecha_publicacion.desc())
                .limit(dias + 1)  # +1 para saber si hay más
                .offset(offset_dias)
            )
        ).scalars().all()
        has_more = len(fechas) > dias
        fechas = fechas[:dias]
        if not fechas:
            return {"ediciones": [], "has_more": False}

        rows = (
            await session.execute(
                select(Norma)
                .where(Norma.fecha_publicacion.in_(fechas), *filters)
                .order_by(Norma.fecha_publicacion.desc(), Norma.id.desc())
            )
        ).scalars().all()

    por_fecha: dict = {f: {"destacados": [], "tramite": []} for f in fechas}
    resumen: dict = {f: {} for f in fechas}
    for n in rows:
        raw = n.raw if isinstance(n.raw, dict) else {}
        bucket = (
            "tramite"
            if es_tramite(n.tipo, n.titulo, tags=n.tags, tipo_linea=raw.get("tipo_linea"))
            else "destacados"
        )
        por_fecha[n.fecha_publicacion][bucket].append(n)
        r = resumen[n.fecha_publicacion]
        r[n.tipo] = r.get(n.tipo, 0) + 1

    out = []
    for f in fechas:
        destacados = sorted(
            por_fecha[f]["destacados"], key=lambda n: (PESO_TIPO.get(n.tipo, 9), -n.id)
        )
        tramite = por_fecha[f]["tramite"]
        out.append(
            {
                "fecha": f.isoformat(),
                "resumen": resumen[f],
                "destacados_total": len(destacados),
                "tramite_total": len(tramite),
                "destacados": [
                    NormaListItem.model_validate(n) for n in destacados[:_MAX_DESTACADOS]
                ],
                "tramite": [NormaListItem.model_validate(n) for n in tramite[:_MAX_TRAMITE]],
            }
        )
    return {"ediciones": out, "has_more": has_more}


@router.get("", response_model=NormaPage)
async def list_normas(
    tipo: str | None = Query(None, description="DNU|DECRETO|LEY|RESOLUCION|DISPOSICION|PROYECTO|COMUNICACION|OTRA"),
    impacto: str | None = Query(None, description="alto|medio|bajo"),
    sector: str | None = Query(None),
    emisor: str | None = Query(None, description="organismo canónico: ARCA|CNV|BCRA|…"),
    source: str | None = Query(
        None, description="códigos de fuente separados por coma: bora_primera,infoleg|bocaba|bopba"
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
) -> NormaPage:
    Session = get_sessionmaker()
    filters = []
    if tipo:
        filters.append(Norma.tipo == tipo)
    if impacto:
        filters.append(Norma.impacto == impacto)
    if sector:
        filters.append(Norma.sector == sector)
    if emisor:
        filters.append(Norma.emisor == emisor)
    _apply_source(filters, source)

    async with Session() as session:
        # El COUNT sin filtros es un seq scan de las ~543k filas (~1,5 s) y solo
        # alimenta el contador de paginación: lo cacheamos por combinación de
        # filtros. La query de items, en cambio, sale del índice ix_norma_feed.
        async def _count() -> int:
            return (
                await session.execute(select(func.count()).select_from(Norma).where(*filters))
            ).scalar_one()

        cache_key = f"normas:count:{tipo}|{impacto}|{sector}|{emisor}|{source}"
        total = await cached(cache_key, _COUNT_TTL, _count)
        query = (
            select(Norma)
            .where(*filters)
            .order_by(Norma.fecha_publicacion.desc().nullslast(), Norma.id.desc())
            .limit(limit)
            .offset(offset)
        )
        if tipo == "DNU":
            # El tracker bicameral viaja con el listado solo cuando se pide DNU.
            query = select(Norma, DnuTracking.estado_bicameral).join(
                DnuTracking, DnuTracking.norma_id == Norma.id, isouter=True
            ).where(*filters).order_by(
                Norma.fecha_publicacion.desc().nullslast(), Norma.id.desc()
            ).limit(limit).offset(offset)
            rows = (await session.execute(query)).all()
            items = []
            for norma, estado_bicameral in rows:
                item = NormaListItem.model_validate(norma)
                item.estado_bicameral = estado_bicameral
                items.append(item)
        else:
            rows = (await session.execute(query)).scalars().all()
            items = [NormaListItem.model_validate(r) for r in rows]

    return NormaPage(items=items, total=int(total or 0), limit=limit, offset=offset)


@router.get("/{norma_id}", response_model=NormaDetail)
async def get_norma(norma_id: int) -> NormaDetail:
    Session = get_sessionmaker()
    async with Session() as session:
        row = (
            await session.execute(
                select(Norma, SourceCatalog.name, SourceCatalog.code)
                .join(SourceCatalog, SourceCatalog.id == Norma.source_id, isouter=True)
                .where(Norma.id == norma_id)
            )
        ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Norma no encontrada")
    norma, fuente, fuente_code = row
    detail = NormaDetail.model_validate(norma)
    detail.fuente = fuente
    detail.fuente_code = fuente_code
    if isinstance(norma.raw, dict):
        movs = norma.raw.get("movimientos")
        if isinstance(movs, list) and movs:
            detail.movimientos = movs
    return detail
