"""BO CABA — Boletín Oficial de la Ciudad de Buenos Aires.

A diferencia del BO nacional (scrape HTML), CABA expone una **API REST JSON**
documentada (verificado 2026-06):

- ``GET /obtenerBoletin/{parametro}/{carga_datos}`` — ``parametro`` = fecha
  ``dd-mm-yyyy`` (ó número de boletín); ``carga_datos=true`` trae el boletín
  completo: ``boletin`` (fecha, numero, url PDF) + ``normas`` anidadas por
  **Poder → Tipo → Organismo → [norma]**. Cada norma:
  ``{nombre:"Ley N° 6960", sumario, id_norma, url_norma}``.

Una sola llamada por día trae todas las publicaciones. Ingestamos los actos
normativos (Poderes Legislativo/Ejecutivo/Judicial + Órganos de Control) y
salteamos Edictos, Licitaciones y Comunicados (avisos, no normas).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime
from typing import Any, Self

from vigia_connectors._http import get_json, make_client

BOCABA_BASE = "https://api-restboletinoficial.buenosaires.gob.ar"
USER_AGENT = "vigia/0.1 (+https://vigia.openarg.org)"

# Poderes cuyas publicaciones SON normas (el resto del árbol son avisos:
# "Edictos Oficiales", "Edictos Particulares", "Licitaciones", "Comunicados y Avisos").
_PODERES_NORMA = {
    "poder legislativo",
    "poder ejecutivo",
    "poder judicial",
    "organos de control",
}

# Tipo CABA (clave del árbol) -> slug de la taxonomía de Vigía (TIPOS_NORMA).
_TIPO_MAP = {
    "ley": "LEY",
    "decreto": "DECRETO",
    "resolucion": "RESOLUCION",
    "resolucion comunal": "RESOLUCION",
    "resolucion de directorio": "RESOLUCION",
    "disposicion": "DISPOSICION",
    "acordada": "OTRA",
    "acta": "OTRA",
}

_NUM_RE = re.compile(r"N[°º]\s*([\d][\d./-]*)")


def _norm(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip().lower()


def _map_tipo(tipo_raw: str) -> str:
    return _TIPO_MAP.get(_norm(tipo_raw), "OTRA")


def _parse_numero(nombre: str | None) -> str | None:
    m = _NUM_RE.search(nombre or "")
    if not m:
        return None
    return m.group(1).rstrip("/.-") or None


def _parse_fecha(value: str | None) -> Date | None:
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


@dataclass(slots=True)
class BoCabaNorma:
    id_norma: str
    tipo: str  # slug ya mapeado (LEY|DECRETO|RESOLUCION|DISPOSICION|OTRA)
    numero: str | None
    nombre: str  # denominación formal: "Ley N° 6960"
    sumario: str | None
    fecha: Date | None
    poder: str
    organismo: str | None
    url: str | None

    @property
    def external_id(self) -> str:
        return self.id_norma

    @property
    def titulo(self) -> str:
        return self.sumario or self.nombre

    def detect_sector(self) -> str | None:
        from vigia_connectors.sectores import detect_sector

        return detect_sector(self.sumario, self.organismo, self.nombre)


def parse_boletin(data: dict[str, Any], fecha_fallback: Date) -> list[BoCabaNorma]:
    """Aplana el árbol Poder→Tipo→Organismo→[norma]. Función pura (testable).

    Solo conserva los poderes normativos; saltea avisos/edictos/licitaciones.
    """
    if not isinstance(data, dict):
        return []
    boletin = data.get("boletin") or {}
    fecha = _parse_fecha(boletin.get("fecha_publicacion")) or fecha_fallback
    root = (data.get("normas") or {}).get("normas") or {}
    out: list[BoCabaNorma] = []
    for poder, tipos in root.items():
        if _norm(poder) not in _PODERES_NORMA or not isinstance(tipos, dict):
            continue
        for tipo_raw, orgs in tipos.items():
            if not isinstance(orgs, dict):
                continue
            tipo = _map_tipo(tipo_raw)
            for organismo, lst in orgs.items():
                if not isinstance(lst, list):
                    continue
                for n in lst:
                    if not isinstance(n, dict):
                        continue
                    id_norma = str(n.get("id_norma") or "").strip()
                    nombre = (n.get("nombre") or "").strip()
                    if not id_norma or not nombre:
                        continue
                    sumario = (n.get("sumario") or "").strip() or None
                    out.append(
                        BoCabaNorma(
                            id_norma=id_norma,
                            tipo=tipo,
                            numero=_parse_numero(nombre),
                            nombre=nombre,
                            sumario=sumario[:4000] if sumario else None,
                            fecha=fecha,
                            poder=poder.strip(),
                            organismo=(organismo or "").strip() or None,
                            url=(n.get("url_norma") or "").strip() or None,
                        )
                    )
    return out


class BoCabaClient:
    def __init__(self, *, timeout: float = 45.0) -> None:
        self._client = make_client(
            base_url=BOCABA_BASE,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_edicion(self, fecha: Date) -> list[BoCabaNorma]:
        """Normas del boletín de una fecha (una sola llamada trae todo el día).

        Días sin edición (feriados, fines de semana) devuelven lista vacía.
        """
        try:
            data = await get_json(
                self._client, f"/obtenerBoletin/{fecha:%d-%m-%Y}/true"
            )
        except Exception:
            return []
        return parse_boletin(data, fecha)

    async def fetch_recent(self, dias: int = 5) -> list[BoCabaNorma]:
        """Las ediciones de los últimos `dias` (idempotente; cubre días tardíos)."""
        from datetime import timedelta

        hoy = datetime.now().date()
        out: list[BoCabaNorma] = []
        seen: set[str] = set()
        for d in range(dias):
            for n in await self.fetch_edicion(hoy - timedelta(days=d)):
                if n.id_norma in seen:
                    continue
                seen.add(n.id_norma)
                out.append(n)
        return out
