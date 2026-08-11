"""`/v1/normas` — listado y detalle del corpus para integradores.

Dos recorridos, y la diferencia importa:

- **feed** (default): `fecha_publicacion DESC, id DESC`. Es "las últimas normas",
  el orden con el que uno mira. Sale del índice `ix_norma_feed`.
- **sync** (`updated_since=...`): `updated_at ASC, id ASC`. Es "qué cambió desde
  la última vez". Sale del índice `ix_norma_updated` (migración 0009).

`updated_since` **cambia el orden** porque es la única forma de que una
sincronización incremental sea correcta: recorriendo por `updated_at` hacia
adelante, una fila que se modifica en medio del recorrido se mueve al final y se
vuelve a ver — nunca se saltea. Ordenado por fecha de publicación pasaría lo
contrario, que es el modo de falla que no podemos tener.
"""
from __future__ import annotations

from datetime import date as Date
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import BigInteger, Date as SaDate, DateTime, literal, select, tuple_

from vigia_api.core.cache import cached
from vigia_api.core.db import get_sessionmaker
from vigia_api.routers.v1 import cursor as cur
from vigia_api.routers.v1.schemas import NormaPublic, NormaPublicDetail, NormaPublicPage
from vigia_shared.models import DnuTracking, Norma, SourceCatalog

router = APIRouter(prefix="/v1/normas", tags=["v1 · normas"])

# `source_catalog` tiene una decena de filas y solo cambia cuando se suma una
# fuente: se cachea el mapa entero en vez de joinear en cada listado.
_SOURCES_TTL = 300.0

# Sentinela para arrancar el tramo de normas sin `fecha_publicacion` (ver
# `_pagina_feed`): mayor que cualquier id real, así la primera página del tramo
# no excluye nada.
_ID_MAX = 2**63 - 1


def _mal_pedido(detalle: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detalle)


async def _codigos_de_fuente() -> dict[int, str]:
    async def _cargar() -> dict[int, str]:
        Session = get_sessionmaker()
        async with Session() as session:
            filas = (await session.execute(select(SourceCatalog.id, SourceCatalog.code))).all()
        return {fila[0]: fila[1] for fila in filas}

    return await cached("v1:sources:codes", _SOURCES_TTL, _cargar)


def _filtros_base(
    *,
    tipo: str | None,
    impacto: str | None,
    sector: str | None,
    emisor: str | None,
    jurisdiccion: str | None,
    source: str | None,
    codigos: dict[int, str],
) -> list:
    filtros = []
    if tipo:
        filtros.append(Norma.tipo == tipo)
    if impacto:
        filtros.append(Norma.impacto == impacto)
    if sector:
        filtros.append(Norma.sector == sector)
    if emisor:
        filtros.append(Norma.emisor == emisor)
    if jurisdiccion:
        filtros.append(Norma.jurisdiccion == jurisdiccion)
    if source:
        pedidos = [c.strip() for c in source.split(",") if c.strip()]
        conocidos = set(codigos.values())
        # Un código mal escrito devolvería cero filas sin decir por qué, y del
        # otro lado eso se lee como "no hubo novedades". Mejor romper fuerte.
        desconocidos = sorted(set(pedidos) - conocidos)
        if desconocidos:
            raise _mal_pedido(f"fuente_desconocida: {','.join(desconocidos)}")
        if pedidos:
            filtros.append(
                Norma.source_id.in_([i for i, c in codigos.items() if c in set(pedidos)])
            )
    return filtros


def _a_utc(momento: datetime) -> datetime:
    """Un timestamp sin zona se interpreta como UTC, no como hora local del server."""
    if momento.tzinfo is None:
        return momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc)


def _clave_timestamp(clave: str | None) -> datetime:
    try:
        return _a_utc(datetime.fromisoformat(clave))  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise _mal_pedido("cursor_invalido") from exc


def _clave_fecha(clave: str | None) -> Date:
    try:
        return Date.fromisoformat(clave)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise _mal_pedido("cursor_invalido") from exc


async def _traer(filtros: list, orden: tuple, cantidad: int) -> list[Norma]:
    Session = get_sessionmaker()
    async with Session() as session:
        return list(
            (
                await session.execute(
                    select(Norma).where(*filtros).order_by(*orden).limit(cantidad)
                )
            )
            .scalars()
            .all()
        )


async def _hay_sin_fecha(filtros: list) -> bool:
    Session = get_sessionmaker()
    async with Session() as session:
        fila = (
            await session.execute(
                select(Norma.id)
                .where(Norma.fecha_publicacion.is_(None), *filtros)
                .limit(1)
            )
        ).first()
    return fila is not None


async def _pagina_sync(
    filtros: list, desde: datetime, clave: str | None, id_: int | None, limit: int
) -> tuple[list[Norma], bool, str | None]:
    filtros = [*filtros, Norma.updated_at >= desde]
    if id_ is not None:
        filtros.append(
            tuple_(Norma.updated_at, Norma.id)
            > tuple_(literal(_clave_timestamp(clave), DateTime(timezone=True)),
                     literal(id_, BigInteger))
        )
    filas = await _traer(filtros, (Norma.updated_at.asc(), Norma.id.asc()), limit + 1)
    has_more = len(filas) > limit
    filas = filas[:limit]
    if not has_more:
        return filas, False, None
    ultima = filas[-1]
    siguiente = cur.encode(
        modo=cur.MODO_SYNC, clave=_a_utc(ultima.updated_at).isoformat(), id_=ultima.id
    )
    return filas, True, siguiente


async def _pagina_feed(
    base: list, clave: str | None, id_: int | None, limit: int
) -> tuple[list[Norma], bool, str | None]:
    """Feed en dos tramos: primero las normas con fecha, después las que no.

    Partirlo así es lo que mantiene la paginación barata. La alternativa —
    un solo recorrido con `... OR fecha_publicacion IS NULL` — deja de ser una
    comparación de tupla pura, y sin eso Postgres no puede usar el predicado
    como punto de arranque en `ix_norma_feed`: volvería a escanear el índice
    desde el principio en cada página, que es exactamente el costo del `offset`
    que vinimos a sacar.

    Las normas sin fecha son pocas (proyectos recién ingestados, sobre todo),
    pero no se pueden dejar afuera: alguien que recorre el feed entero tiene que
    poder llegar a todo.
    """
    en_tramo_sin_fecha = id_ is not None and clave is None

    if en_tramo_sin_fecha:
        filtros = [*base, Norma.fecha_publicacion.is_(None), Norma.id < id_]
        orden = (Norma.id.desc(),)
    else:
        filtros = [*base, Norma.fecha_publicacion.isnot(None)]
        if id_ is not None:
            filtros.append(
                tuple_(Norma.fecha_publicacion, Norma.id)
                < tuple_(literal(_clave_fecha(clave), SaDate), literal(id_, BigInteger))
            )
        # `.nullslast()` calca `ix_norma_feed` aunque el filtro ya descarte los
        # NULL: si el ORDER BY no es idéntico, el índice deja de matchear.
        orden = (Norma.fecha_publicacion.desc().nullslast(), Norma.id.desc())

    filas = await _traer(filtros, orden, limit + 1)
    has_more = len(filas) > limit
    filas = filas[:limit]

    if has_more:
        ultima = filas[-1]
        clave_sig = None if en_tramo_sin_fecha else ultima.fecha_publicacion.isoformat()
        return filas, True, cur.encode(modo=cur.MODO_FEED, clave=clave_sig, id_=ultima.id)

    if en_tramo_sin_fecha:
        return filas, False, None

    # Se acabaron las normas con fecha: si queda algo en el otro tramo, el
    # cursor salta ahí. Esta consulta corre una sola vez por recorrido completo.
    if await _hay_sin_fecha(base):
        return filas, True, cur.encode(modo=cur.MODO_FEED, clave=None, id_=_ID_MAX)
    return filas, False, None


@router.get("", response_model=NormaPublicPage)
async def list_normas(
    updated_since: datetime | None = Query(
        None,
        description=(
            "ISO 8601 (`2026-08-01T00:00:00Z`). Devuelve lo modificado desde ese "
            "momento **ordenado por `updated_at` ascendente**, para sincronización "
            "incremental. Sin zona horaria se interpreta UTC."
        ),
    ),
    cursor: str | None = Query(
        None, description="`next_cursor` de la página anterior. No mezclar cursores entre órdenes."
    ),
    tipo: str | None = Query(
        None, description="DNU|DECRETO|LEY|RESOLUCION|DISPOSICION|PROYECTO|COMUNICACION|OTRA"
    ),
    impacto: str | None = Query(None, description="alto|medio|bajo"),
    sector: str | None = Query(None),
    emisor: str | None = Query(None, description="organismo canónico: ARCA|CNV|BCRA|…"),
    jurisdiccion: str | None = Query(None),
    source: str | None = Query(
        None, description="códigos de fuente separados por coma: infoleg,bora_primera|bocaba|bopba"
    ),
    limit: int = Query(50, ge=1, le=200),
) -> NormaPublicPage:
    """Listado paginado por cursor.

    **No devuelve `total` a propósito.** Contar el corpus filtrado es un seq scan
    de medio millón de filas y a un cliente que sincroniza no le sirve de nada;
    el recorrido termina cuando `has_more` es `false`. Para volúmenes hay
    `/stats`.

    **Sincronizar**: primera corrida con `updated_since` bien atrás (o sin él, si
    querés el corpus entero en orden de feed), después seguí `next_cursor` hasta
    `has_more: false`, y guardá el mayor `updated_at` que hayas visto. En la
    corrida siguiente pedí desde **ese valor menos unos minutos**: el solapamiento
    cubre las filas que se commitean con un `updated_at` apenas anterior al
    instante en que vos cortaste. Los ids son estables, así que reprocesar una
    fila repetida es un upsert y no un duplicado.
    """
    # El cursor se valida antes de tocar la base: un cursor podrido no tiene por
    # qué costar un round-trip a Postgres.
    modo = cur.MODO_SYNC if updated_since is not None else cur.MODO_FEED
    clave: str | None = None
    id_: int | None = None
    if cursor:
        clave, id_ = cur.decode(cursor, modo_esperado=modo)

    codigos = await _codigos_de_fuente()
    base = _filtros_base(
        tipo=tipo,
        impacto=impacto,
        sector=sector,
        emisor=emisor,
        jurisdiccion=jurisdiccion,
        source=source,
        codigos=codigos,
    )

    if modo == cur.MODO_SYNC:
        filas, has_more, siguiente = await _pagina_sync(
            base, _a_utc(updated_since), clave, id_, limit  # type: ignore[arg-type]
        )
    else:
        filas, has_more, siguiente = await _pagina_feed(base, clave, id_, limit)

    data = []
    for norma in filas:
        item = NormaPublic.model_validate(norma)
        item.fuente = codigos.get(norma.source_id)
        data.append(item)
    return NormaPublicPage(data=data, has_more=has_more, next_cursor=siguiente)


@router.get("/{norma_id}", response_model=NormaPublicDetail)
async def get_norma(norma_id: int) -> NormaPublicDetail:
    """Detalle de una norma por su `id` de Vigía."""
    Session = get_sessionmaker()
    async with Session() as session:
        fila = (
            await session.execute(
                select(Norma, SourceCatalog.code, DnuTracking.estado_bicameral)
                .join(SourceCatalog, SourceCatalog.id == Norma.source_id, isouter=True)
                .join(DnuTracking, DnuTracking.norma_id == Norma.id, isouter=True)
                .where(Norma.id == norma_id)
            )
        ).first()
    if fila is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="norma_no_encontrada")
    norma, code, estado_bicameral = fila
    detalle = NormaPublicDetail.model_validate(norma)
    detalle.fuente = code
    detalle.estado_bicameral = estado_bicameral
    return detalle
