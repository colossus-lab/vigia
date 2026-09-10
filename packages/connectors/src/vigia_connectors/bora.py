"""BORA — Boletín Oficial de la República Argentina (boletinoficial.gob.ar).

Fuente de frescura diaria: el BO publica cada día hábil de madrugada, mientras
que el dataset InfoLEG llega con ~2 semanas de lag. No hay API documentada;
el sitio renderiza server-side un HTML estable (verificado 2026-06):

- Listado por sección y fecha: ``GET /seccion/{seccion}/{yyyymmdd}``
  (sin fecha = edición del día). Cada aviso es un
  ``<a href="/detalleAviso/{seccion}/{id}/{yyyymmdd}">`` que contiene
  ``p.item`` (organismo) y dos ``p.item-detalle`` (tipo+número, sumario).
- Detalle: ``GET /detalleAviso/{seccion}/{id}/{fecha}`` con el texto completo
  en ``div#cuerpoDetalleAviso``.

Fallback de existencia de edición: PDF del día en
``https://s3.arsat.com.ar/cdn-bo-001/pdf-del-dia/primera.pdf`` (no se parsea).
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime
from typing import Self

from bs4 import BeautifulSoup

from vigia_connectors._http import get_text, make_client

BORA_BASE = "https://www.boletinoficial.gob.ar"
USER_AGENT = "vigia/0.1 (+https://vigia.openarg.org)"

# El listado sirve como máximo 100 avisos por sección y fecha, y el HTML NO trae
# paginación: verificado 2026-09-10, no hay `data-page`, ni "ver más", ni
# `totalItems` en el markup. O sea que en las ediciones pesadas perdemos la cola
# sin que nada falle. Medido ese día sobre la 1ª sección del 2026-09-08: el
# listado devolvió 100 avisos (IDs 347019→347118), pero los IDs siguientes
# existían para esa misma fecha hasta ~347265 — o sea ~247 avisos reales, 100
# ingeridos. La 2ª sección pega el tope TODOS los días hábiles.
#
# Resolverlo requiere otra vía de acceso (recorrido por rango de ID del día, o
# el buscador del sitio). Hasta entonces, lo mínimo es que deje de ser
# silencioso: `listado_truncado` es la señal que las tasks suben a
# /health/sources en vez de reportar "ok" sobre una edición incompleta.
LISTADO_TOPE = 100

# "Decreto 436/2026" -> (tipo, numero). El número puede no estar (p.ej. "Fe de erratas").
_TIPO_NUM_RE = re.compile(r"^\s*(?P<tipo>[A-Za-zÁÉÍÓÚÑáéíóúñü.\s]+?)\s*(?P<numero>\d[\d./-]*)?\s*$")

# Señales de DNU en el texto del aviso (los DNU se dictan por art. 99 inc. 3 CN
# y/o se remiten a la Comisión Bicameral Permanente de la ley 26.122).
_DNU_RE = re.compile(
    r"art[íi]culo\s*99[^.]{0,80}?inciso\s*3|necesidad\s+y\s+urgencia|comisi[óo]n\s+bicameral\s+permanente",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(slots=True)
class BoraAviso:
    aviso_id: str  # numérico en 1ª; alfanumérico en 2ª (p.ej. "A1500779")
    seccion: str  # "primera" | "segunda" | "tercera"
    fecha: Date
    organismo: str | None  # 1ª: organismo emisor; 2ª: razón social
    tipo_linea: str | None  # "Decreto 436/2026", "Resolución 52/2026", ...
    sumario: str | None
    rubro: str | None = None  # header h5.seccion-rubro vigente ("CONVOCATORIAS", ...)

    @property
    def url(self) -> str:
        return f"{BORA_BASE}/detalleAviso/{self.seccion}/{self.aviso_id}/{self.fecha:%Y%m%d}"

    @property
    def numero(self) -> str | None:
        m = _TIPO_NUM_RE.match(self.tipo_linea or "")
        return m.group("numero") if m else None

    def tipo_slug(self) -> str:
        """Clasifica por la línea tipo+número del listado (misma taxonomía que InfoLEG).

        Los DNU salen como "Decreto" — se promueven a DNU mirando el texto del
        detalle (ver `looks_like_dnu`); si no, InfoLEG corrige al alcanzar.
        """
        t = (self.tipo_linea or "").strip().lower()
        if t.startswith("ley"):
            return "LEY"
        if t.startswith("decisi"):  # decisión administrativa -> acto del ejecutivo
            return "DECRETO"
        if t.startswith("decreto"):
            return "DNU" if "necesidad" in t else "DECRETO"
        if t.startswith("resol"):
            return "RESOLUCION"
        if t.startswith("disposi"):
            return "DISPOSICION"
        return "OTRA"

    def detect_sector(self) -> str | None:
        from vigia_connectors.sectores import detect_sector

        return detect_sector(self.organismo, self.tipo_linea, self.sumario)


def looks_like_dnu(texto: str | None) -> bool:
    return bool(texto and _DNU_RE.search(texto))


def parse_seccion_html(html: str, seccion: str, fecha: Date) -> list[BoraAviso]:
    """Parsea el listado de una sección. Función pura — testeable con fixtures.

    Los rubros vienen como headers ``h5.seccion-rubro`` intercalados entre los
    avisos: se trackean en orden de documento y se asignan al aviso siguiente.
    """
    soup = BeautifulSoup(html, "lxml")
    avisos: list[BoraAviso] = []
    prefix = f"/detalleAviso/{seccion}/"
    rubro: str | None = None
    for el in soup.select(f'h5.seccion-rubro, a[href^="{prefix}"]'):
        if el.name == "h5":
            rubro = el.get_text(" ", strip=True) or rubro
            continue
        href = el.get("href", "")
        m = re.match(rf"{re.escape(prefix)}([A-Za-z]?\d+)/(\d{{8}})", href)
        if not m:
            continue
        aviso_id, fecha_str = m.group(1), m.group(2)
        try:
            fecha_aviso = datetime.strptime(fecha_str, "%Y%m%d").date()
        except ValueError:
            fecha_aviso = fecha
        organismo_el = el.select_one("p.item")
        detalles = [d.get_text(" ", strip=True) for d in el.select("p.item-detalle")]
        if organismo_el is None and not detalles:
            continue  # link de navegación/banner sin contenido de aviso
        avisos.append(
            BoraAviso(
                aviso_id=aviso_id,
                seccion=seccion,
                fecha=fecha_aviso,
                organismo=organismo_el.get_text(" ", strip=True) if organismo_el else None,
                tipo_linea=detalles[0] if detalles else None,
                sumario=detalles[1] if len(detalles) > 1 else (detalles[0] if detalles else None),
                rubro=rubro,
            )
        )
    # El mismo aviso puede aparecer dos veces (link con ?anexos=1): dedup por id.
    seen: set[str] = set()
    unique = []
    for av in avisos:
        if av.aviso_id in seen:
            continue
        seen.add(av.aviso_id)
        unique.append(av)
    return unique


def parse_detalle_texto(html: str) -> str | None:
    """Extrae el texto completo del aviso desde div#cuerpoDetalleAviso."""
    soup = BeautifulSoup(html, "lxml")
    cuerpo = soup.select_one("#cuerpoDetalleAviso")
    if cuerpo is None:
        return None
    return cuerpo.get_text("\n", strip=True) or None


class BoraClient:
    def __init__(self, *, timeout: float = 60.0, max_concurrency: int = 4) -> None:
        self._client = make_client(
            base_url=BORA_BASE, timeout=timeout, headers={"User-Agent": USER_AGENT}
        )
        self._sem = asyncio.Semaphore(max_concurrency)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_seccion(self, seccion: str = "primera", fecha: Date | None = None) -> list[BoraAviso]:
        """Avisos del listado de una sección para una fecha (default: edición del día).

        Días sin edición (feriados, fines de semana) devuelven lista vacía.
        """
        path = f"/seccion/{seccion}"
        target = fecha or Date.today()
        if fecha is not None:
            path += f"/{fecha:%Y%m%d}"
        html = await get_text(self._client, path)
        return parse_seccion_html(html, seccion, target)

    async def fetch_detalle_texto(self, aviso: BoraAviso) -> str | None:
        """Texto completo de un aviso (para detección de DNU, etc.)."""
        async with self._sem:
            html = await get_text(
                self._client, f"/detalleAviso/{aviso.seccion}/{aviso.aviso_id}/{aviso.fecha:%Y%m%d}"
            )
        return parse_detalle_texto(html)


def listado_truncado(avisos: list[BoraAviso]) -> bool:
    """True si el listado de esa fecha pegó el tope del sitio (faltan avisos).

    Es un piso, no un conteo exacto: `parse_seccion_html` dedupea por `aviso_id`
    (los links ``?anexos=1`` repiten el mismo aviso), así que si una edición
    truncada trajera duplicados el parseo podría quedar en 99 y no disparar.
    Preferimos ese falso negativo raro antes que un umbral más flojo que
    empiece a marcar ediciones sanas: como señal de warn, subestimar es barato.
    """
    return len(avisos) >= LISTADO_TOPE
