"""BO PBA — Boletín Oficial de la Provincia de Buenos Aires.

No hay API: el sitio sirve cada sección de una edición como **PDF**
(verificado 2026-06). Cada edición tiene 3 secciones con IDs consecutivos
(OFICIAL < JUDICIAL < JURISPRUDENCIA): ``GET /secciones/{id}/descargar`` →
``application/pdf``. El índice ``/ediciones-anteriores`` lista las ediciones
recientes con sus tríos de secciones.

Ingestamos **solo la sección OFICIAL** (decisión: PBA solo normas). El PDF tiene
capa de texto (pypdf, sin OCR) y un sumario por rubros. Segmentación:

1. Extraer texto, limpiar el encabezado/pie corrido de cada página.
2. Trackear el rubro vigente (marcador ``◢ RUBRO``) y el organismo (línea
   institucional en mayúsculas).
3. Anclar en la dateline ``LA PLATA, BUENOS AIRES`` (1 por acto real — las citas
   en prosa no la tienen) y leer el header ``TIPO N° <num>`` hacia atrás.
4. Conservar solo los rubros de norma (RESOLUCIONES, DISPOSICIONES, etc.);
   saltear SOCIEDADES, LICITACIONES, EDICTOS, VARIOS y las secciones
   JUDICIAL/JURISPRUDENCIA.

El cert SSL del sitio está roto → el cliente va con ``verify_ssl=False``.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime
from typing import Self

from bs4 import BeautifulSoup
from pypdf import PdfReader

from vigia_connectors._http import get_text, make_client

BOPBA_BASE = "https://boletinoficial.gba.gob.ar"
USER_AGENT = "vigia/0.1 (+https://vigia.openarg.org)"

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Rubros del sumario que SON normas (el resto son avisos/edictos/societario).
NORM_RUBROS = {
    "RESOLUCIONES", "RESOLUCIONES FIRMA CONJUNTA", "DISPOSICIONES",
    "DISPOSICIONES FIRMA CONJUNTA", "DECRETOS", "DECRETOS FIRMA CONJUNTA",
    "LEYES", "DECRETOS-LEY",
}

# Encabezado/pie corrido que pypdf arrastra de cada página.
_JUNK_RE = re.compile(
    r"^BOLET[IÍ]N OFICIAL DE LA PROVINCIA.*$|^La Plata\s*>.*$|"
    r"^SECCI[ÓO]N\s+OFICIAL\s*>\s*p[áa]gina.*$|^Secci[óo]n\s*$|^Oficial\s*$|"
    r"^A[ÑN]O\s+C.*N[º°]\s*\d+\s*$|^\s*\d{1,3}\s*$",
    re.MULTILINE,
)
_RUBRO_RE = re.compile(r"◢\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ]{2,45})")
_ORG_RE = re.compile(
    r"^((?:MINISTERIO|MINISTRO|SECRETAR[IÍ]A|SUBSECRETAR[IÍ]A|DIRECCI[ÓO]N|"
    r"INSTITUTO|ORGANISMO|AGENCIA|TRIBUNAL|CONSEJO|CONTADUR[IÍ]A|TESORER[IÍ]A|"
    r"FISCAL[IÍ]A|ASESOR[IÍ]A|HONORABLE|GOBIERNO|JEFATURA|JUNTA)[A-ZÁÉÍÓÚÑ ,.()-]{3,70})$",
    re.MULTILINE,
)
_DATELINE_RE = re.compile(r"LA\s+PLATA,\s+BUENOS\s+AIRES")
_HEADER_RE = re.compile(
    r"(RESOLUCI[ÓO]N(?:\s+(?:DE\s+)?FIRMA\s+CONJUNTA)?|DISPOSICI[ÓO]N|DECRETO(?:-LEY)?|LEY)\s+"
    r"N[°º]\s*([0-9][\w./-]*)",
    re.IGNORECASE,
)
_EDICION_FECHA_RE = re.compile(r"La Plata,\s+\w+\s+(\d{1,2})\s+de\s+([a-zA-ZáéíóúÁÉÍÓÚ]+)\s+de\s+(\d{4})")
_VISTO_RE = re.compile(r"VISTO\s*(.+?)(?:CONSIDERANDO|POR ELLO|$)", re.DOTALL)
# Prefijo de expediente del VISTO ("el EX-… mediante el cual", "el expediente … por el cual").
_EXP_PREFIX_RE = re.compile(r"^\W*(?:el|la|los)\s+(?:EX|expediente)\b.*?\bcual\b\s*", re.IGNORECASE | re.DOTALL)
# Fecha del encabezado corrido que pypdf puede colar inline al cruzar página.
_PAGE_DATE_RE = re.compile(
    r"\b(?:lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo)\s+\d{1,2}\s+de\s+"
    r"[a-záéíóú]+\s+de\s+\d{4}\b",
    re.IGNORECASE,
)


_LABEL = {"RESOLUCION": "Resolución", "DISPOSICION": "Disposición", "DECRETO": "Decreto", "LEY": "Ley"}


def _tipo_slug(s: str) -> str:
    s = s.upper()
    if s.startswith("RESOLUCI"):
        return "RESOLUCION"
    if s.startswith("DISPOSICI"):
        return "DISPOSICION"
    if s.startswith("DECRETO"):
        return "DECRETO"
    if s == "LEY":
        return "LEY"
    return "OTRA"


def parse_edicion_fecha(text: str) -> Date | None:
    """Fecha de la edición desde el masthead ('La Plata, lunes 29 de junio de 2026')."""
    m = _EDICION_FECHA_RE.search(text)
    if not m:
        return None
    mes = _MESES.get(m.group(2).lower())
    if not mes:
        return None
    try:
        return Date(int(m.group(3)), mes, int(m.group(1)))
    except ValueError:
        return None


def _at(positions: list[tuple[int, str]], pos: int) -> str | None:
    cur = None
    for p, v in positions:
        if p <= pos:
            cur = v
        else:
            break
    return cur


@dataclass(slots=True)
class BoPbaNorma:
    numero: str
    tipo: str
    organismo: str | None
    rubro: str
    titulo: str
    resumen: str | None
    fecha: Date | None
    url: str | None

    @property
    def external_id(self) -> str:
        return self.numero

    def detect_sector(self) -> str | None:
        from vigia_connectors.sectores import detect_sector

        return detect_sector(self.titulo, self.organismo, self.resumen)


def parse_oficial(pdf_text: str, *, fecha: Date | None, url: str | None) -> list[BoPbaNorma]:
    """Segmenta el texto de la sección OFICIAL en normas. Función pura (testable)."""
    text = _JUNK_RE.sub("", pdf_text)
    fecha = fecha or parse_edicion_fecha(pdf_text)
    rubros = [(m.start(), re.sub(r"\s+", " ", m.group(1)).strip()) for m in _RUBRO_RE.finditer(text)]
    orgs = [(m.start(), re.sub(r"\s+", " ", m.group(1)).strip()) for m in _ORG_RE.finditer(text)]

    out: list[BoPbaNorma] = []
    seen: set[str] = set()
    for m in _DATELINE_RE.finditer(text):
        pos = m.start()
        rubro = _at(rubros, pos)
        if rubro not in NORM_RUBROS:
            continue
        back = text[max(0, pos - 320):pos]
        headers = list(_HEADER_RE.finditer(back))
        if not headers:
            continue
        h = headers[-1]  # el header más cercano a la dateline
        numero = h.group(2)
        if numero in seen:
            continue
        seen.add(numero)
        tipo = _tipo_slug(h.group(1))
        organismo = _at(orgs, pos)
        # excerpt = subject del VISTO (lo que describe de qué trata el acto)
        cuerpo = text[pos:pos + 4000]
        v = _VISTO_RE.search(cuerpo)
        subj = re.sub(r"\s+", " ", (v.group(1) if v else "")).strip()
        subj = _PAGE_DATE_RE.sub("", subj)
        subj = re.sub(r"\s+", " ", _EXP_PREFIX_RE.sub("", subj)).strip()[:800]
        if subj:
            subj = subj[0].upper() + subj[1:]
        titulo = subj[:200] if subj else f"{_LABEL.get(tipo, tipo.title())} N° {numero}"
        resumen = subj if len(subj) > 200 else None
        out.append(
            BoPbaNorma(
                numero=numero,
                tipo=tipo,
                organismo=organismo,
                rubro=rubro,
                titulo=titulo,
                resumen=resumen,
                fecha=fecha,
                url=url,
            )
        )
    return out


class BoPbaClient:
    def __init__(self, *, timeout: float = 90.0) -> None:
        self._client = make_client(
            base_url=BOPBA_BASE,
            timeout=timeout,
            verify_ssl=False,  # cert roto del sitio
            headers={"User-Agent": USER_AGENT},
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def recent_oficial_ids(self, n: int = 5) -> list[int]:
        """IDs de la sección OFICIAL de las últimas `n` ediciones.

        Cada edición tiene 3 secciones con IDs consecutivos; la OFICIAL es el
        menor de cada trío. El índice las lista de la más reciente a la más vieja.
        """
        html = await get_text(self._client, "/ediciones-anteriores")
        soup = BeautifulSoup(html, "lxml")
        ids: list[int] = []
        for a in soup.select('a[href*="/secciones/"]'):
            m = re.search(r"/secciones/(\d+)/", a.get("href", ""))
            if m:
                v = int(m.group(1))
                if v not in ids:
                    ids.append(v)
        ids.sort(reverse=True)
        oficiales = [min(ids[i:i + 3]) for i in range(0, len(ids), 3) if ids[i:i + 3]]
        return oficiales[:n]

    async def fetch_oficial(self, section_id: int) -> list[BoPbaNorma]:
        """Descarga y parsea la sección OFICIAL de una edición."""
        resp = await self._client.get(f"/secciones/{section_id}/descargar")
        resp.raise_for_status()
        text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(resp.content)).pages)
        url = f"{BOPBA_BASE}/secciones/{section_id}/ver"
        return parse_oficial(text, fecha=None, url=url)

    async def fetch_recent(self, dias: int = 3) -> list[BoPbaNorma]:
        """Normas de las últimas `dias` ediciones OFICIAL (dedup por número)."""
        out: list[BoPbaNorma] = []
        seen: set[str] = set()
        for sid in await self.recent_oficial_ids(dias):
            try:
                normas = await self.fetch_oficial(sid)
            except Exception:
                continue
            for n in normas:
                if n.numero in seen:
                    continue
                seen.add(n.numero)
                out.append(n)
        return out
