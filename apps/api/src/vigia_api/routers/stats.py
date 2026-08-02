"""KPIs y agregaciones para el Dashboard y el Tracker DNU."""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import text

from vigia_api.core.cache import cached
from vigia_api.core.db import get_sessionmaker
from vigia_shared.schemas import (
    DashboardStats,
    DnuAnio,
    DnuStats,
    EmisorStat,
    OrganismoStat,
    RecentStats,
    SectorStat,
    SeriesPoint,
    TipoStat,
)

router = APIRouter(prefix="/stats", tags=["stats"])

# La ingesta corre una vez por día (beat 03:00/08:00 ART), así que 5' de
# desactualización en los KPIs es invisible y ahorra el scan en cada visita.
_DASHBOARD_TTL = 300.0


@router.get("/dashboard", response_model=DashboardStats)
async def dashboard() -> DashboardStats:
    """KPIs globales. Cacheado: son tres seq scans de la tabla entera.

    `COUNT(*)` y los dos `GROUP BY` recorren las ~543k filas sí o sí (no hay
    índice que evite un agregado global), ~4,5 s en total. Como la ingesta es
    diaria, servir un valor de hasta `_DASHBOARD_TTL` segundos de antigüedad no
    cambia nada de lo que se muestra.
    """
    return await cached("stats:dashboard", _DASHBOARD_TTL, _dashboard_uncached)


async def _dashboard_uncached() -> DashboardStats:
    Session = get_sessionmaker()
    async with Session() as session:
        total = (await session.execute(text("SELECT COUNT(*) FROM norma"))).scalar_one()
        por_tipo = (
            await session.execute(
                text("SELECT tipo, COUNT(*) c FROM norma GROUP BY tipo ORDER BY c DESC")
            )
        ).all()
        por_sector = (
            await session.execute(
                text(
                    "SELECT sector, COUNT(*) c FROM norma "
                    "WHERE sector IS NOT NULL GROUP BY sector ORDER BY c DESC"
                )
            )
        ).all()
        rec = (
            await session.execute(
                text(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE fecha_publicacion >= current_date - 7)  AS semana,
                      COUNT(*) FILTER (WHERE fecha_publicacion >= current_date - 14
                                         AND fecha_publicacion <  current_date - 7)  AS semana_anterior,
                      COUNT(*) FILTER (WHERE fecha_publicacion >= current_date - 30) AS mes,
                      COUNT(*) FILTER (WHERE fecha_publicacion >= current_date - 60
                                         AND fecha_publicacion <  current_date - 30) AS mes_anterior,
                      COUNT(*) FILTER (WHERE tipo = 'PROYECTO'
                                         AND fecha_publicacion >= current_date - 30) AS proyectos_30d,
                      COUNT(*) FILTER (WHERE tipo = 'DNU'
                                         AND fecha_publicacion >= date_trunc('year', current_date)) AS dnu_anio
                    FROM norma
                    WHERE fecha_publicacion >= current_date - 60
                       OR (tipo = 'DNU' AND fecha_publicacion >= date_trunc('year', current_date))
                    """
                )
            )
        ).one()
    return DashboardStats(
        total_normas=int(total or 0),
        por_tipo=[TipoStat(tipo=r[0], cantidad=int(r[1])) for r in por_tipo],
        por_sector=[SectorStat(sector=r[0], cantidad=int(r[1])) for r in por_sector],
        recientes=RecentStats(
            semana=int(rec.semana or 0),
            semana_anterior=int(rec.semana_anterior or 0),
            mes=int(rec.mes or 0),
            mes_anterior=int(rec.mes_anterior or 0),
            proyectos_30d=int(rec.proyectos_30d or 0),
            dnu_anio=int(rec.dnu_anio or 0),
        ),
    )


@router.get("/series", response_model=list[SeriesPoint])
async def series(
    months: int = Query(24, ge=3, le=120),
    granularity: str = Query("month", pattern="^(month|week)$"),
) -> list[SeriesPoint]:
    """Producción normativa por período y tipo (pulso regulatorio).

    granularity=week devuelve semanas ISO (campo `mes` = lunes de la semana,
    YYYY-MM-DD) acotadas a los últimos ~`months`*4.3 semanas.
    """
    Session = get_sessionmaker()
    if granularity == "week":
        sql = """
            SELECT to_char(date_trunc('week', fecha_publicacion), 'YYYY-MM-DD') AS periodo,
                   tipo, COUNT(*) c
            FROM norma
            WHERE fecha_publicacion >= date_trunc('week', current_date) - make_interval(weeks => :periods)
              AND fecha_publicacion < date_trunc('week', current_date) + interval '1 week'
            GROUP BY 1, 2
            ORDER BY 1
        """
        params = {"periods": months * 4}
    else:
        sql = """
            SELECT to_char(date_trunc('month', fecha_publicacion), 'YYYY-MM') AS periodo,
                   tipo, COUNT(*) c
            FROM norma
            WHERE fecha_publicacion >= date_trunc('month', current_date) - make_interval(months => :periods)
              AND fecha_publicacion < date_trunc('month', current_date) + interval '1 month'
            GROUP BY 1, 2
            ORDER BY 1
        """
        params = {"periods": months}

    async with Session() as session:
        rows = (await session.execute(text(sql), params)).all()

    by_period: dict[str, dict[str, int]] = {}
    for periodo, tipo, c in rows:
        by_period.setdefault(periodo, {})[tipo] = int(c)
    return [
        SeriesPoint(mes=p, total=sum(tipos.values()), por_tipo=tipos)
        for p, tipos in sorted(by_period.items())
    ]


@router.get("/organismos", response_model=list[OrganismoStat])
async def organismos(
    days: int = Query(90, ge=7, le=365),
    limit: int = Query(10, ge=3, le=30),
) -> list[OrganismoStat]:
    """Top organismos emisores del período reciente (quién está regulando).

    Agrupa por (jurisdicción, nombre normalizado) y NO por el texto crudo. El
    `organismo` viene como texto libre de cada fuente y la misma entidad llega
    escrita distinto: `Jefatura de Gabinete de Ministros` y `JEFATURA DE GABINETE
    DE MINISTROS` sumaban por separado — 32.175 normas partidas en dos. Había 14
    grupos así, 44.479 normas, y el ranking los mostraba como organismos
    distintos.

    La jurisdicción va en la clave a propósito: el `MINISTERIO DE SALUD` nacional,
    el de CABA y el de PBA son entidades distintas y NO deben fusionarse.

    Se muestra la grafía más frecuente del grupo (`mode()`) en vez de la versión
    en mayúsculas, que se lee como un grito.

    La misma lógica vive en `vigia_shared.organismos.clave_organismo` para el lado
    Python; si cambian las reglas, hay que tocar las dos.
    """
    Session = get_sessionmaker()
    async with Session() as session:
        rows = (
            await session.execute(
                text(
                    r"""
                    SELECT mode() WITHIN GROUP (ORDER BY organismo) AS organismo,
                           COALESCE(jurisdiccion, '') AS jurisdiccion,
                           COUNT(*) c
                    FROM norma
                    WHERE organismo IS NOT NULL AND btrim(organismo) <> ''
                      AND fecha_publicacion >= current_date - make_interval(days => :days)
                    GROUP BY COALESCE(jurisdiccion, ''),
                             upper(btrim(regexp_replace(
                                 regexp_replace(organismo, '\s+', ' ', 'g'),
                                 '[\s\-–—:;,\.]+$', '')))
                    ORDER BY c DESC
                    LIMIT :limit
                    """
                ),
                {"days": days, "limit": limit},
            )
        ).all()
    return [
        OrganismoStat(organismo=r[0], jurisdiccion=r[1] or None, cantidad=int(r[2]))
        for r in rows
    ]


@router.get("/emisores", response_model=list[EmisorStat])
async def emisores() -> list[EmisorStat]:
    """Conteo por emisor canónico (ARCA, CNV, …) — alimenta el facet del feed."""
    Session = get_sessionmaker()
    async with Session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT emisor, COUNT(*) c FROM norma "
                    "WHERE emisor IS NOT NULL GROUP BY emisor ORDER BY c DESC"
                )
            )
        ).all()
    return [EmisorStat(emisor=r[0], cantidad=int(r[1])) for r in rows]


@router.get("/dnu", response_model=DnuStats)
async def dnu_stats() -> DnuStats:
    Session = get_sessionmaker()
    async with Session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT estado_bicameral, COUNT(*) c "
                    "FROM dnu_tracking GROUP BY estado_bicameral"
                )
            )
        ).all()
        historico = (
            await session.execute(
                text(
                    """
                    SELECT EXTRACT(YEAR FROM fecha_publicacion)::int AS anio, COUNT(*) c
                    FROM norma
                    WHERE tipo = 'DNU' AND fecha_publicacion IS NOT NULL
                    GROUP BY 1
                    ORDER BY 1
                    """
                )
            )
        ).all()
    by = {r[0]: int(r[1]) for r in rows}
    return DnuStats(
        total=sum(by.values()),
        aprobados=by.get("aprobado", 0),
        rechazados=by.get("rechazado", 0),
        pendientes=by.get("pendiente", 0),
        dictaminados=by.get("dictaminado", 0),
        sin_tratamiento=by.get("sin_tratamiento", 0),
        historico=[DnuAnio(anio=int(r[0]), cantidad=int(r[1])) for r in historico],
    )
