"""Contrato público de `/v1`. Deliberadamente separado de `vigia_shared.schemas`.

Los schemas de `vigia_shared` son el contrato **interno** entre la API y el web:
se mueven cuando el web necesita otro campo, y así tiene que ser. Si `/v1`
reusara esos modelos, cualquier ajuste de UI cambiaría la respuesta que ve un
integrador — sin que nadie lo note en el diff.

Por eso viven acá, en el paquete del router: agregar un campo público pasa a ser
un acto explícito, y sacarlo, un breaking change que se ve.

Criterio de qué se expone: lo que es dato de la norma. Quedan afuera `raw` (el
crudo de cada fuente, sin forma estable), `search_vector` (interno), `entidades`
en el listado (hoy vacío) y `bora_seccion` (detalle de scraping, no de la norma).
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class NormaPublic(BaseModel):
    """Una norma en el listado público."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Identificador estable de Vigía.")
    external_id: str = Field(description="Id de la norma en su fuente de origen.")
    fuente: str | None = Field(
        default=None, description="Código de la fuente: infoleg|bora_primera|hcdn|bocaba|bopba|…"
    )

    tipo: str = Field(description="DNU|DECRETO|LEY|RESOLUCION|DISPOSICION|PROYECTO|COMUNICACION|OTRA")
    numero: str | None = None
    titulo: str
    resumen: str | None = Field(default=None, description="Sumario oficial, tal como lo publica la fuente.")
    resumen_ia: str | None = Field(
        default=None,
        description="Resumen generado por IA. Puede faltar y no reemplaza al texto oficial.",
    )

    fecha_publicacion: date | None = None
    jurisdiccion: str | None = None
    sector: str | None = None
    emisor: str | None = Field(default=None, description="Organismo canónico: ARCA|CNV|BCRA|…")
    organismo: str | None = Field(default=None, description="Organismo tal como lo nombra la fuente.")
    estado: str | None = None
    impacto: str | None = Field(default=None, description="alto|medio|bajo (estimado por Vigía).")
    tags: list[str] | None = None
    url: str | None = Field(default=None, description="Link al texto en la fuente oficial.")

    updated_at: datetime = Field(
        description="Última modificación en Vigía. Es la columna que ordena `updated_since`."
    )


class NormaPublicDetail(NormaPublic):
    """El detalle suma lo que no vale la pena mandar por cada fila del listado."""

    entidades: list[str] | None = None
    ingested_at: datetime | None = Field(
        default=None, description="Cuándo entró a Vigía por primera vez."
    )
    estado_bicameral: str | None = Field(
        default=None,
        description=(
            "Solo DNU: sin_tratamiento|pendiente|dictaminado|aprobado|rechazado. "
            "El trámite ante la Comisión Bicameral."
        ),
    )


class NormaPublicPage(BaseModel):
    """Página keyset. Sin `total`: ver el docstring de `list_normas`."""

    data: list[NormaPublic]
    has_more: bool = Field(description="Si hay más páginas después de esta.")
    next_cursor: str | None = Field(
        default=None,
        description=(
            "Se pasa como `cursor` para traer la página siguiente. "
            "Es null exactamente cuando `has_more` es false."
        ),
    )
