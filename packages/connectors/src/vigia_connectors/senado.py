"""Proyectos del Senado de la Nación (HSN) — scrape del buscador parlamentario.

A diferencia de Diputados (CKAN en datos.hcdn.gob.ar), el Senado no publica un
dataset de proyectos: hay que scrapear el buscador Symfony de
`senado.gob.ar/parlamentario/parlamentaria/`. Flujo: GET la página (trae el token
CSRF + cookie de sesión) → POST la búsqueda avanzada → GET `?page=N` para paginar
(el filtro persiste en la sesión) → GET el detalle por expediente para fecha+autores.

Para no duplicar lo que ya trae el connector HCDN, por defecto solo se ingieren
los expedientes originados en el Senado (`origen == "S"`); los venidos de Diputados
(`CD`) ya están cubiertos por `hcdn_proyectos`.
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

    async def buscar(self, tipo_codigo: str, page: int = 1) -> list[SenadoProyecto]:
        """Una página de resultados para un tipo. page=1 hace el POST; >1 pagina."""
        if page <= 1:
            await self._ensure_token()
            data = {
                "busqueda_proyectos[palabra]": "",
                "busqueda_proyectos[opcion]": "1",
                "busqueda_proyectos[palabra2]": "",
                "busqueda_proyectos[expedienteTipo]": tipo_codigo,
                "busqueda_proyectos[autor]": "",
                "busqueda_proyectos[comision]": "",
                "busqueda_proyectos[tipoDocumento]": "",
                "busqueda_proyectos[expedienteLugar]": "",
                "busqueda_proyectos[_token]": self._token or "",
            }
            r = await self._client.post(_BUSCAR, data=data)
        else:
            r = await self._client.get(_BUSCAR, params={"page": page})
        return parse_listado(r.text)

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

    async def fetch_recientes(
        self,
        *,
        tipos: tuple[str, ...] = TIPOS_PROYECTO,
        max_pages: int = 3,
        solo_origen: tuple[str, ...] | None = ("S",),
        con_detalle: bool = True,
    ) -> list[SenadoProyecto]:
        """Proyectos recientes (páginas iniciales = números más altos) por tipo.

        `solo_origen=("S",)` deja afuera los venidos de Diputados (ya en HCDN).
        El upsert idempotente hace barato re-traer las primeras páginas a diario.
        """
        vistos: dict[str, SenadoProyecto] = {}
        for tc in tipos:
            for page in range(1, max_pages + 1):
                items = await self.buscar(tc, page)
                if not items:
                    break
                for p in items:
                    if solo_origen and p.origen not in solo_origen:
                        continue
                    vistos[p.external_id] = p
        proyectos = list(vistos.values())
        if con_detalle and proyectos:
            await asyncio.gather(*(self.fetch_detalle(p) for p in proyectos))
        return proyectos
