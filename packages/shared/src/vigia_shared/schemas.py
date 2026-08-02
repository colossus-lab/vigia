"""Schemas Pydantic v2 compartidos (respuestas de API)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class NormaBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: str
    numero: str | None = None
    titulo: str
    resumen: str | None = None
    resumen_ia: str | None = None
    fecha_publicacion: date | None = None
    jurisdiccion: str | None = None
    sector: str | None = None
    emisor: str | None = None
    organismo: str | None = None
    estado: str | None = None
    impacto: str | None = None
    bora_seccion: str | None = None
    tags: list[str] | None = None
    url: str | None = None
    # Solo poblado para DNU (join a dnu_tracking):
    # sin_tratamiento | pendiente | dictaminado | aprobado | rechazado
    estado_bicameral: str | None = None


class NormaListItem(NormaBase):
    """Versión liviana para feed/búsqueda (sin entidades ni raw)."""


class NormaDetail(NormaBase):
    """Detalle completo de una norma."""

    entidades: list[str] | None = None
    ingested_at: datetime | None = None
    fuente: str | None = None  # source_catalog.name — de dónde salió esta norma
    fuente_code: str | None = None
    # Timeline de tramitación (PROYECTO): últimos movimientos HCDN, de raw.
    movimientos: list[dict] | None = None


class NormaPage(BaseModel):
    items: list[NormaListItem]
    total: int
    limit: int
    offset: int


class SectorStat(BaseModel):
    sector: str
    cantidad: int


class TipoStat(BaseModel):
    tipo: str
    cantidad: int


class RecentStats(BaseModel):
    """Conteos de actividad reciente con su período anterior para deltas."""

    semana: int
    semana_anterior: int
    mes: int
    mes_anterior: int
    proyectos_30d: int
    dnu_anio: int


class DashboardStats(BaseModel):
    total_normas: int
    por_tipo: list[TipoStat]
    por_sector: list[SectorStat]
    recientes: RecentStats | None = None


class SeriesPoint(BaseModel):
    """Un mes de la serie temporal; counts por tipo + total."""

    mes: str  # YYYY-MM
    total: int
    por_tipo: dict[str, int]


class OrganismoStat(BaseModel):
    organismo: str
    # Parte de la identidad, no un adorno: hay un MINISTERIO DE SALUD nacional,
    # uno de CABA y uno de PBA. Sin esto el ranking muestra tres filas iguales.
    jurisdiccion: str | None = None
    cantidad: int


class EmisorStat(BaseModel):
    emisor: str
    cantidad: int


class DnuAnio(BaseModel):
    anio: int
    cantidad: int


class DnuStats(BaseModel):
    total: int
    aprobados: int
    rechazados: int
    pendientes: int  # vigentes a la espera de dictamen (post ley 26.122)
    dictaminados: int = 0  # con dictamen de la Bicameral, sin resolución de ambas cámaras
    sin_tratamiento: int = 0  # pre ley 26.122: nunca van a tener dictamen
    historico: list[DnuAnio] = []
