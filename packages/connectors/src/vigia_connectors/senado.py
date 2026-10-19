"""Proyectos del Senado de la Nación (HSN) — scrape del buscador parlamentario.

A diferencia de Diputados (CKAN en datos.hcdn.gob.ar), el Senado no publica un
dataset de proyectos: hay que scrapear el buscador Symfony de
`senado.gob.ar/parlamentario/parlamentaria/`. Flujo: GET la página (trae el token
CSRF + cookie de sesión) → POST la búsqueda avanzada → GET `?page=N` para paginar
(el filtro persiste en la sesión) → GET el detalle por expediente para fecha+autores.

Para no duplicar lo que ya trae el connector HCDN se dejan afuera los venidos de
Diputados (`CD`), que ya están en `hcdn_proyectos`. Sí entran los que ingresan por
el Senado desde el Ejecutivo (`PE`, `JGM`) u oficiales varios (`OV`): sin ellos las
votaciones del Senado sobre proyectos del Ejecutivo (p.ej. `PE-159/25-PL`) no
tienen contra qué cruzarse. Ver `ORIGENES_INGESTA`.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date as Date
from typing import Self

from bs4 import BeautifulSoup

from vigia_connectors._http import make_client
from vigia_connectors.sectores import detect_sector

SENADO_BASE = "https://www.senado.gob.ar"
_LANDING = "/parlamentario/parlamentaria/"
_BUSCAR = "/parlamentario/parlamentaria/avanzada"

# Tipos de expediente que son "proyectos" (el resto: mensajes, acuerdos, etc.).
TIPOS_PROYECTO = ("PL", "PR", "PD", "PC", "DE")
# Orígenes que se ingieren. Afuera: `CD` (ya en hcdn_proyectos) y `P`
# (particulares: peticiones, no proyectos de legisladores ni del Ejecutivo).
ORIGENES_INGESTA = ("S", "PE", "JGM", "OV")

_TIPO_NOMBRE = {
    "PL": "ley", "PR": "resolución", "PD": "declaración",
    "PC": "comunicación", "DE": "decreto",
}

_RE_TOKEN = re.compile(r'name="busqueda_proyectos\[_token\]"\s+value="([^"]+)"')
_RE_VEREXP = re.compile(r"/parlamentario/comisiones/verExp/(\d+)\.(\d+)/([^/]+)/([^/?\"'\s]+)")
_RE_FECHA = re.compile(r"\b(\d{2})-(\d{2})-(\d{4})\b")


@dataclass(slots=True)
class SenadoProyecto:
    """Un expediente del Senado. Los campos de detalle se completan aparte."""

    numero: str          # "1040"
    anio: str            # "26"
    tipo_codigo: str     # PL | PR | PD | PC | DE
    origen: str          # S | CD | PE | JGM | P | OV
    extracto: str        # título/sumario
    fecha: Date | None = None
    autores: list[str] | None = None

    @property
    def external_id(self) -> str:
        # El trío (número, origen, tipo) identifica de forma única el expediente.
        return f"{self.numero}/{self.anio}-{self.origen}-{self.tipo_codigo}"

    @property
    def url(self) -> str:
        return f"{SENADO_BASE}/parlamentario/comisiones/verExp/{self.numero}.{self.anio}/{self.origen}/{self.tipo_codigo}"

    @property
    def tipo_proyecto(self) -> str | None:
        return _TIPO_NOMBRE.get(self.tipo_codigo)

    def tipo_slug(self) -> str:
        return "PROYECTO"

    def detect_sector(self) -> str | None:
        return detect_sector(self.extracto)


def parse_listado(html: str) -> list[SenadoProyecto]:
    """Parsea la tabla de resultados (`Listado de Proyectos`): Exp|Tipo|Origen|Extracto."""
    soup = BeautifulSoup(html, "html.parser")
    tabla = soup.find("table", attrs={"summary": re.compile("Listado de Proyectos", re.I)})
    if tabla is None:
        return []
    out: list[SenadoProyecto] = []
    for tr in tabla.find_all("tr"):
        a = tr.find("a", href=_RE_VEREXP)
        if a is None:
            continue
        m = _RE_VEREXP.search(a["href"])
        if not m:
            continue
        numero, anio, origen, tipo_codigo = m.groups()
        tds = tr.find_all("td")
        extracto = tds[-1].get_text(" ", strip=True) if tds else a.get_text(" ", strip=True)
        out.append(SenadoProyecto(
            numero=numero, anio=anio, origen=origen,
            tipo_codigo=tipo_codigo, extracto=extracto,
        ))
    return out


def parse_detalle(html: str) -> dict:
    """Extrae fecha (Mesa de Entradas) y autores de la página de detalle."""
    soup = BeautifulSoup(html, "html.parser")

    # Fecha: la tabla cuyo encabezado tiene MESA DE ENTRADAS + DADO CUENTA. La 1ª
    # fecha de esa tabla es el ingreso del expediente (la usamos como publicación).
    fecha: Date | None = None
    for tabla in soup.find_all("table"):
        head = tabla.get_text(" ", strip=True).upper()
        if "MESA DE ENTRADAS" in head and "DADO CUENTA" in head:
            fechas = _RE_FECHA.findall(tabla.get_text(" "))
            if fechas:
                d, mn, y = fechas[0]
                try:
                    fecha = Date(int(y), int(mn), int(d))
                except ValueError:
                    fecha = None
            break

    # Autores: el bloque tras "Listado de Autores", formato "Apellido , Nombre".
    autores: list[str] | None = None
    anchor = soup.find(string=re.compile("Listado de Autores", re.I))
    if anchor is not None:
        cont = anchor.find_parent(["div", "td", "section", "table"]) or anchor.parent
        crudo = cont.get_text("\n") if cont else ""
        crudo = crudo.split("Listado de Autores", 1)[-1]
        # cortar en la próxima sección conocida
        for stop in ("Fechas en Dir", "Trámite", "Tramite", "Giro", "DIR. GRAL"):
            crudo = crudo.split(stop, 1)[0]
        nombres = [
            re.sub(r"\s+", " ", n).strip(" ,")
            for n in re.split(r"\n", crudo)
            if n.strip(" ,\t")
        ]
        # juntar pares "Apellido" / ", Nombre" partidos por el markup
        joined = re.sub(r"\s+", " ", " ".join(nombres)).strip()
        autores = [a.strip() for a in re.split(r"\s{2,}|;", joined) if a.strip()] or None
        if autores:
            autores = autores[:6]

    return {"fecha": fecha, "autores": autores}


# Tope duro de páginas por búsqueda: el corte normal es la primera página vacía,
# esto es por si el sitio cambia y empieza a repetir la última.
_MAX_PAGINAS = 1000


def form_busqueda(
    tipo_codigo: str, *, origen: str = "", anio: int | None = None, token: str = ""
) -> dict[str, str]:
    """Campos del POST de la búsqueda avanzada.

    `expedienteLugar` filtra por origen (S, PE, JGM, OV, CD...) y
    `expedienteNumeroPos` por año del expediente (2026, 2025...).
    """
    return {
        "busqueda_proyectos[palabra]": "",
        "busqueda_proyectos[opcion]": "1",
        "busqueda_proyectos[palabra2]": "",
        "busqueda_proyectos[expedienteTipo]": tipo_codigo,
        "busqueda_proyectos[autor]": "",
        "busqueda_proyectos[comision]": "",
        "busqueda_proyectos[tipoDocumento]": "",
        "busqueda_proyectos[expedienteLugar]": origen,
        "busqueda_proyectos[expedienteNumeroPre]": "",
        "busqueda_proyectos[expedienteNumeroPos]": str(anio) if anio else "",
        "busqueda_proyectos[_token]": token,
    }


class SenadoClient:
    """Cliente async del buscador del Senado (mantiene token CSRF + cookie de sesión)."""

    def __init__(self, *, timeout: float = 30.0, concurrency: int = 4) -> None:
        self._client = make_client(
            base_url=SENADO_BASE,
            timeout=timeout,
            headers={"User-Agent": "vigia/0.1 (+https://vigia.openarg.org)"},
        )
        self._sem = asyncio.Semaphore(concurrency)
        self._token: str | None = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _ensure_token(self) -> None:
        r = await self._client.get(_LANDING)
        m = _RE_TOKEN.search(r.text)
        self._token = m.group(1) if m else None

    async def buscar(
        self, tipo_codigo: str, page: int = 1, *, origen: str = "", anio: int | None = None
    ) -> list[SenadoProyecto]:
        """Una página de resultados. page=1 hace el POST con el filtro; >1 pagina
        (el filtro queda en la sesión, así que las búsquedas van de a una)."""
        if page <= 1:
            await self._ensure_token()
            data = form_busqueda(tipo_codigo, origen=origen, anio=anio, token=self._token or "")
            r = await self._client.post(_BUSCAR, data=data)
        else:
            r = await self._client.get(_BUSCAR, params={"page": page})
        return parse_listado(r.text)

    async def _buscar_paginas(
        self, tipo_codigo: str, origen: str, *, anio: int | None, max_pages: int | None
    ) -> list[SenadoProyecto]:
        """Todas las páginas de una búsqueda, hasta `max_pages` o hasta que venga una
        vacía (el sitio devuelve 200 con la tabla vacía después de la última)."""
        tope = min(max_pages or _MAX_PAGINAS, _MAX_PAGINAS)
        out: list[SenadoProyecto] = []
        for page in range(1, tope + 1):
            items = await self.buscar(tipo_codigo, page, origen=origen, anio=anio)
            if not items:
                break
            out.extend(items)
        return out

    async def fetch_detalle(self, p: SenadoProyecto) -> None:
        # Un detalle flaky (el sitio del Senado es lento/inestable desde el EC2 y
        # los timeouts httpx llegan sin mensaje) NO debe abortar toda la ingesta:
        # el proyecto entra igual con fecha/autores nulos y un run posterior los
        # completa (upsert idempotente). Antes, un solo timeout en el asyncio.gather
        # tumbaba la corrida entera y la marcaba 'error' con mensaje vacío.
        try:
            async with self._sem:
                r = await self._client.get(p.url)
            info = parse_detalle(r.text)
            p.fecha = info["fecha"]
            p.autores = info["autores"]
        except Exception:
            return

    async def _buscar(
        self,
        *,
        tipos: tuple[str, ...],
        origenes: tuple[str, ...],
        anio: int | None,
        max_pages: int | None,
        con_detalle: bool,
    ) -> list[SenadoProyecto]:
        vistos: dict[str, SenadoProyecto] = {}
        for tc in tipos:
            for origen in origenes:
                for p in await self._buscar_paginas(tc, origen, anio=anio, max_pages=max_pages):
                    # El filtro del sitio ya acota el origen; esto es por las dudas.
                    if p.origen in origenes:
                        vistos[p.external_id] = p
        proyectos = list(vistos.values())
        if con_detalle and proyectos:
            await asyncio.gather(*(self.fetch_detalle(p) for p in proyectos))
        return proyectos

    async def fetch_recientes(
        self,
        *,
        tipos: tuple[str, ...] = TIPOS_PROYECTO,
        max_pages: int = 3,
        origenes: tuple[str, ...] = ORIGENES_INGESTA,
        con_detalle: bool = True,
    ) -> list[SenadoProyecto]:
        """Proyectos recientes: las primeras páginas de cada tipo, **origen por origen**.

        Una búsqueda sin filtro de origen devuelve todo mezclado y lo dominan los
        de origen S (~2.000-6.000 por año contra ~50-90 del Ejecutivo): con 3
        páginas, los PE recientes no aparecían nunca. Filtrando por origen, cada
        uno trae sus propias páginas. El upsert idempotente hace barato re-traer
        las primeras páginas a diario.
        """
        return await self._buscar(
            tipos=tipos, origenes=origenes, anio=None, max_pages=max_pages, con_detalle=con_detalle
        )

    async def fetch_anio(
        self,
        anio: int,
        *,
        tipos: tuple[str, ...] = TIPOS_PROYECTO,
        origenes: tuple[str, ...] = ORIGENES_INGESTA,
        con_detalle: bool = True,
    ) -> list[SenadoProyecto]:
        """Todos los proyectos de un año (por año del expediente), sin tope de
        páginas: es para backfill. Medido 2026-10: S trae ~2.000-6.500 por año y
        PE ~50-90, a ~0,9 s por página."""
        return await self._buscar(
            tipos=tipos, origenes=origenes, anio=anio, max_pages=None, con_detalle=con_detalle
        )
