"""Actividad de la Cámara de Diputados — scrape de www.hcdn.gob.ar.

Lo que PASA en Diputados (agenda de comisiones, sesiones y lo que se trató en
cada una). Va a tablas propias de la sección Congreso, nunca a `norma`.

Tres páginas, todas HTML server-rendered y sin API:

- `/comisiones/agenda/`: tabla `#agendaComisiones` con la semana en curso. Un
  `<thead>` por día ("martes 20 de octubre del 2026", trae el año) y una fila
  por reunión. Las sesiones de recinto aparecen en la misma tabla.
- `/sesiones/`: un acordeón por período parlamentario (1983→) con un link
  `sesion.html?id=&reunion=&periodo=` por reunión. De acá salen período y
  reunión para armar la URL del Boletín de Asuntos Tratados.
- `/secparl/dsecretaria/bat/bat.jsp?periodo=&reunion=&sesion=`: el Boletín de
  Asuntos Tratados (BAT), una fila por asunto con O.D., expedientes, tipo, tema
  y sanción. Es un fragmento HTML (sin `<html>`); si la sesión todavía no tiene
  boletín devuelve el wrapper vacío con 200.

**`votaciones.hcdn.gob.ar` NO se toca**: tiene reCAPTCHA v3 y no se esquiva.
Por eso Diputados no tiene voto nominal y muestra resultados por expediente.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date as Date
from datetime import datetime, time, timedelta, timezone
from typing import Self
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, Comment, Tag

from vigia_connectors._http import get_text, make_client
from vigia_connectors.hcdn import HcdnSesionCsv
from vigia_shared.expedientes import extraer_expedientes

HCDN_BASE = "https://www.hcdn.gob.ar"
AGENDA_PATH = "/comisiones/agenda/"
SESIONES_PATH = "/sesiones/"
BAT_PATH = "/secparl/dsecretaria/bat/bat.jsp"

# Argentina no tiene horario de verano desde 2009: offset fijo, sin tzdata.
ART = timezone(timedelta(hours=-3))

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_RE_DIA = re.compile(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+(?:del?\s+)?(\d{4})", re.IGNORECASE)
_RE_HORA = re.compile(r"\b(\d{1,2})[:.](\d{2})\b")
_RE_REUN = re.compile(r"reunion\.html\?reun=(\d+)&(?:amp;)?prosecretaria=(\w+)")
_RE_REUN_PDF = re.compile(r"/comisiones/reuniones/(\d+)/archivo/")
# Último tramo de "Sala 1 - Anexo "A" - Informativa" cuando es el tipo de reunión.
_RE_TIPO_REUNION = re.compile(
    r"^(informativa|constitutiva|ordinaria|extraordinaria|especial|asesores|conjunta|plenario|t[eé]cnica)\b",
    re.IGNORECASE,
)


def _ws(s: str | None) -> str:
    return " ".join((s or "").replace("\xa0", " ").split())


def _lineas(td: Tag) -> list[str]:
    """Texto de una celda en líneas, respetando `<p>` y `<br>` pero no los tags
    inline: en el BAT un expediente puede venir partido en `4153<em>-D-2026</em>`
    y separarlo por tag lo rompería."""
    for br in td.find_all("br"):
        br.replace_with("\n")
    for blk in td.find_all(["p", "div", "h3", "h4", "h5", "li"]):
        blk.insert_after("\n")
    lineas = (_ws(x) for x in td.get_text("").split("\n"))
    return [x for x in lineas if x]


def _vacio(s: str | None) -> bool:
    return _ws(s) in ("", "-", "—", "–")


# ───────────────────────────── Agenda de comisiones ─────────────────────────────


@dataclass(slots=True)
class HcdnReunion:
    external_id: str  # reunId de parlamentaria; si falta, hash estable
    fecha_hora: datetime
    comision: str  # nombres de las comisiones, separados por coma
    comisiones: list[str]
    slugs: list[str]
    sala: str | None
    tipo: str | None
    temario: str | None
    expedientes: list[str]
    url_citacion: str | None
    reun_id: str | None
    leyenda: str | None = None


@dataclass(slots=True)
class AgendaHcdn:
    reuniones: list[HcdnReunion]
    # Las sesiones de recinto que trae la misma tabla: no son reuniones de
    # comisión (la sesión entra por el listado de sesiones).
    recinto: list[dict] = field(default_factory=list)
    dias: list[Date] = field(default_factory=list)


def _parse_dia(texto: str) -> Date | None:
    m = _RE_DIA.search(texto or "")
    if not m:
        return None
    mes = _MESES.get(m[2].lower())
    if not mes:
        return None
    try:
        return Date(int(m[3]), mes, int(m[1]))
    except ValueError:
        return None


def _hash_id(*partes: str) -> str:
    return "h" + hashlib.sha1("|".join(partes).encode("utf-8")).hexdigest()[:20]


def _celda_hora(td: Tag) -> tuple[time | None, str | None, str | None, str | None]:
    """(hora, sala, tipo, leyenda) de la primera celda de una fila de agenda."""
    leyenda_tag = td.find("span", class_="leyenda")
    leyenda = _ws(leyenda_tag.get_text(" ")) if leyenda_tag else ""
    if leyenda_tag:
        leyenda_tag.decompose()
    conjunta = any("CONJUNTA" in _ws(s.get_text()).upper() for s in td.find_all("strong"))
    lineas = _lineas(td)
    hora = None
    if lineas:
        m = _RE_HORA.search(lineas[0])
        if m and 0 <= int(m[1]) < 24:
            hora = time(int(m[1]), int(m[2]))
    resto = [x for x in lineas[1:] if "CONJUNTA" not in x.upper()]
    sala, tipos = None, []
    if resto:
        partes = [p.strip() for p in resto[0].split(" - ")]
        if len(partes) > 1 and _RE_TIPO_REUNION.match(partes[-1]):
            tipos.append(partes.pop())
        sala = " - ".join(partes) or None
    if conjunta:
        tipos.append("Conjunta")
    return hora, sala, (" · ".join(tipos) or None), (leyenda or None)


def parse_agenda(html: str) -> AgendaHcdn:
    """Agenda de la semana (`/comisiones/agenda/`).

    `external_id` = el `reunId` de parlamentaria.hcdn.gob.ar (sale del link
    comentado a `reunion.html?reun=` o del PDF de citación). Si no está, un
    hash de cámara + fecha_hora + comisión: estable mientras no cambien.
    """
    soup = BeautifulSoup(html, "lxml")
    tabla = soup.find(id="agendaComisiones")
    out = AgendaHcdn(reuniones=[])
    if tabla is None:
        return out
    dia: Date | None = None
    for el in tabla.find_all(["thead", "tr"]):
        if el.name == "thead":
            dia = _parse_dia(el.get_text(" "))
            if dia:
                out.dias.append(dia)
            continue
        if el.find_parent("thead") is not None:
            continue
        tds = el.find_all("td", recursive=False)
        if len(tds) < 2 or dia is None:
            continue
        td_hora, td_info = tds[0], tds[1]

        # El reunId viene en un <a> comentado; la prosecretaría dice si es
        # comisión o secretaría parlamentaria (= sesión de recinto).
        reun_id, prosec = None, None
        for c in td_info.find_all(string=lambda s: isinstance(s, Comment)):
            m = _RE_REUN.search(str(c))
            if m:
                reun_id, prosec = m[1], m[2]
            c.extract()
        hora, sala, tipo, leyenda = _celda_hora(td_hora)
        fecha_hora = datetime.combine(dia, hora or time(0, 0), tzinfo=ART)

        links_com = [a for a in td_info.find_all("a", href=True) if "/comisiones/" in a["href"]
                     and "/reuniones/" not in a["href"] and "agenda" not in a["href"]]
        es_recinto = (
            prosec == "secparl"
            or (sala or "").upper().startswith("RECINTO")
            or (not links_com and any("SESI" in _ws(h.get_text()).upper() for h in td_info.find_all("h5")))
        )

        url_citacion = None
        for a in td_info.find_all("a", href=True):
            if _RE_REUN_PDF.search(a["href"]):
                url_citacion = a["href"]
                reun_id = reun_id or _RE_REUN_PDF.search(a["href"])[1]
                a.decompose()

        if es_recinto:
            titulo = next((_ws(h.get_text()) for h in td_info.find_all("h5") if _ws(h.get_text())), None)
            out.recinto.append({
                "fecha_hora": fecha_hora.isoformat(),
                "titulo": titulo,
                "reun_id": reun_id,
                "expedientes": extraer_expedientes(td_info.get_text(" ")),
            })
            continue

        comisiones = [_ws(a.get_text()).rstrip(", ").strip() for a in links_com]
        comisiones = [c for c in comisiones if c]
        slugs = [a["href"].rstrip("/").rsplit("/", 1)[-1] for a in links_com]
        for a in links_com:
            a.decompose()
        temario = _ws(" ".join(_lineas(td_info))) or None
        comision = ", ".join(comisiones) or "Sin comisión"
        external_id = reun_id or _hash_id("D", fecha_hora.isoformat(), comision)
        out.reuniones.append(
            HcdnReunion(
                external_id=external_id,
                fecha_hora=fecha_hora,
                comision=comision[:512],
                comisiones=comisiones,
                slugs=slugs,
                sala=sala,
                tipo=tipo,
                temario=temario,
                expedientes=extraer_expedientes(temario),
                url_citacion=url_citacion,
                reun_id=reun_id,
                leyenda=leyenda,
            )
        )
    return out


def en_receso(d: Date) -> bool:
    """Receso parlamentario aproximado: el período ordinario va del 1/3 al 30/11
    (con prórroga y extraordinarias en dic-feb) y hay receso de invierno en la
    segunda mitad de julio. Solo sirve para no avisar "agenda vacía" en falso."""
    if d.month in (1, 2) or (d.month == 12 and d.day >= 15):
        return True
    return d.month == 7 and d.day >= 15


# ─────────────────────────────── Listado de sesiones ───────────────────────────────


_RE_SESION_LINK = re.compile(r"sesion\.html\?")
_RE_FECHA_LABEL = re.compile(r"\((\d{2})/(\d{2})/(\d{4})\)\s*$")
_RE_NUM_REUNION = re.compile(r"^\s*\d+\s*°\s*Reuni[oó]n\s*-\s*", re.IGNORECASE)
_RE_NUM_SESION = re.compile(r"(\d+)\s*°\s*Sesi[oó]n", re.IGNORECASE)


@dataclass(slots=True)
class HcdnSesionSitio:
    site_id: str
    periodo: int
    reunion: int
    asamblea: bool
    numero_sesion: int | None
    fecha: Date
    tipo: str | None
    label: str
    url: str


def parse_sesiones_listado(html: str) -> tuple[list[HcdnSesionSitio], int]:
    """Links de `/sesiones/`. Devuelve `(sesiones, descartadas)`.

    Label tipo "9° Reunión - 7° Sesión Ordinaria Especial - (21/10/2026)".
    Se descartan las de `reunion=null` (sesiones citadas que no se hicieron,
    la presentación del presupuesto): no tienen reunión ni boletín.
    """
    soup = BeautifulSoup(html, "lxml")
    out: list[HcdnSesionSitio] = []
    descartadas = 0
    for a in soup.find_all("a", href=_RE_SESION_LINK):
        label = _ws(a.get_text(" "))
        q = parse_qs(urlparse(a["href"]).query)
        site_id = (q.get("id") or [""])[0]
        reunion = (q.get("reunion") or [""])[0]
        periodo = (q.get("periodo") or [""])[0]
        mf = _RE_FECHA_LABEL.search(label)
        if not (reunion.isdigit() and periodo.isdigit() and mf):
            descartadas += 1
            continue
        try:
            fecha = Date(int(mf[3]), int(mf[2]), int(mf[1]))
        except ValueError:
            descartadas += 1
            continue
        tipo = _RE_FECHA_LABEL.sub("", label).strip().rstrip("-").strip()
        tipo = _RE_NUM_REUNION.sub("", tipo)
        ms = _RE_NUM_SESION.search(tipo)
        tipo = _ws(re.sub(r"^\d+\s*°\s*", "", tipo)) or None
        out.append(
            HcdnSesionSitio(
                site_id=site_id,
                periodo=int(periodo),
                reunion=int(reunion),
                asamblea=label.upper().startswith("ASAMBLEA"),
                numero_sesion=int(ms[1]) if ms else None,
                fecha=fecha,
                tipo=tipo,
                label=label,
                url=f"{HCDN_BASE}{SESIONES_PATH}{a['href']}",
            )
        )
    return out, descartadas


@dataclass(slots=True)
class HcdnSesion:
    """Sesión combinada (CKAN + sitio), lista para `congreso_sesion`."""

    periodo: int
    reunion: int
    asamblea: bool
    numero_sesion: int | None
    fecha: Date
    tipo: str | None
    url: str | None
    raw: dict

    @property
    def external_id(self) -> str:
        # `{periodo}-{reunion}`; las Asambleas Legislativas numeran aparte
        # (la 1ª reunión del período 144 y la Asamblea del 1/3 son ambas "1").
        return f"{self.periodo}-A{self.reunion}" if self.asamblea else f"{self.periodo}-{self.reunion}"

    @property
    def bat_url(self) -> str | None:
        if self.asamblea:
            return None  # las asambleas no tienen boletín
        return bat_url(self.periodo, self.reunion, self.numero_sesion or 0)


def bat_url(periodo: int, reunion: int, sesion: int) -> str:
    # Las reuniones sin número de sesión (minoría, preparatoria) van con sesion=0.
    return f"{HCDN_BASE}{BAT_PATH}?periodo={periodo}&reunion={reunion}&sesion={sesion}"


def combinar_sesiones(
    csv_rows: Iterable[HcdnSesionCsv], sitio: Iterable[HcdnSesionSitio]
) -> tuple[list[HcdnSesion], int]:
    """Une el dataset CKAN (2008→, con hora de inicio/fin) y el listado del
    sitio (1983→, fecha correcta y link). Devuelve `(sesiones, desfase_dias)`.

    La fecha del sitio coincide con el BAT ("se levanta la sesión" el día
    siguiente); la del CSV viene corrida. El desfase no se hardcodea: se mide
    en cada corrida contra las sesiones que están en las dos fuentes (moda de
    la diferencia) y se aplica a las horas del CSV y a las sesiones que solo
    están en el CSV. Si HCDN corrige el dataset, el desfase pasa a 0 solo.
    """
    csv_by = {(r.periodo, r.asamblea, r.reunion): r for r in csv_rows}
    sitio_by = {(s.periodo, s.asamblea, s.reunion): s for s in sitio}

    difs = Counter(
        (s.fecha - csv_by[k].inicio.date()).days
        for k, s in sitio_by.items()
        if k in csv_by and csv_by[k].inicio is not None
    )
    desfase = difs.most_common(1)[0][0] if difs else 0
    corr = timedelta(days=desfase)

    out: list[HcdnSesion] = []
    for k in sorted(set(csv_by) | set(sitio_by)):
        c, s = csv_by.get(k), sitio_by.get(k)
        inicio = c.inicio + corr if c and c.inicio else None
        fin = c.fin + corr if c and c.fin else None
        if s is not None:
            fecha = s.fecha
        elif inicio is not None:
            fecha = inicio.date()
        else:
            continue
        tipo = s.tipo if s else c.reunion_tipo
        if k[1] and c and c.reunion_tipo and (tipo or "").upper() in ("", "ASAMBLEA LEGISLATIVA"):
            # El sitio a veces rotula solo "Asamblea Legislativa"; el CSV dice cuál.
            tipo = f"Asamblea Legislativa - {c.reunion_tipo}"
        raw: dict = {"asamblea": k[1]}
        if s is not None:
            raw.update({"site_id": s.site_id, "label": s.label})
        if c is not None:
            raw.update({
                "periodo_id": c.periodo_id,
                "reunion_tipo": c.reunion_tipo,
                "inicio": inicio.isoformat() if inicio else None,
                "fin": fin.isoformat() if fin else None,
            })
        ses = HcdnSesion(
            periodo=k[0],
            reunion=k[2],
            asamblea=k[1],
            numero_sesion=(s.numero_sesion if s else None) or (c.sesion_no if c else None),
            fecha=fecha,
            tipo=(tipo or "")[:128] or None,
            url=s.url if s else None,
            raw=raw,
        )
        ses.raw["bat_url"] = ses.bat_url
        out.append(ses)
    return out, desfase


# ─────────────────────────── Boletín de Asuntos Tratados ───────────────────────────


@dataclass(slots=True)
class HcdnAsunto:
    orden: int  # posición en el boletín, desde 1
    clave: str  # expediente principal, O.D. u orden: única dentro de la sesión
    expedientes: list[str]
    orden_del_dia: str | None
    tipo: str | None  # LEY | RESOLUCIÓN | DECLARACIÓN ...
    sumario: str
    resultado: str | None  # APROBADO SIN MODIFICACIONES, RENDIDO ...
    detalle: list[str]  # "Se comunicó al H. Senado", "LEY N° 27.819"...
    links: list[dict]


_RE_OD = re.compile(r"^\s*(\d{1,5})\b")


def _resultado(lineas: list[str]) -> tuple[str | None, list[str]]:
    """La sanción viene partida en `<p>` ("APROBADO SIN" / "MODIFICACIONES")."""
    lineas = [x for x in lineas if not _vacio(x)]
    if not lineas:
        return None, []
    res, i = lineas[0], 1
    while i < len(lineas) and res.upper().endswith((" SIN", " CON", " EN")):
        res = f"{res} {lineas[i]}"
        i += 1
    return res[:255], lineas[i:]


def parse_bat(html: str) -> list[HcdnAsunto]:
    """Asuntos de un Boletín de Asuntos Tratados. Lista vacía si no hay boletín.

    Columnas: Orden del Día Nº | Expediente | Proyecto de | Tema | Sanción.
    La fila final con colspan ("se levanta la sesión") no es un asunto.
    """
    soup = BeautifulSoup(html, "lxml")
    out: list[HcdnAsunto] = []
    claves: set[str] = set()
    for tabla in soup.find_all("table"):
        tbody = tabla.find("tbody") or tabla
        for tr in tbody.find_all("tr", recursive=False):
            if tr.find_parent("thead") is not None:
                continue
            tds = tr.find_all("td", recursive=False)
            if len(tds) != 5:
                continue
            td_od, td_exp, td_tipo, td_tema, td_sancion = tds
            links = [
                {"texto": _ws(a.get_text(" ")), "url": a["href"]}
                for td in (td_tema, td_sancion)
                for a in td.find_all("a", href=True)
            ]
            for a in td_sancion.find_all("a"):
                a.decompose()
            for a in td_tema.find_all("a"):
                a.decompose()

            sumario = _ws(" ".join(_lineas(td_tema)))
            if not sumario or sumario.upper().startswith("T E M A"):
                continue  # encabezado repetido como fila
            od_txt = _ws(" ".join(_lineas(td_od)))
            mod = _RE_OD.match(od_txt)
            orden_del_dia = str(int(mod[1])) if mod else None
            exp_txt = " ".join(_lineas(td_exp))
            expedientes = extraer_expedientes(exp_txt)
            for e in extraer_expedientes(sumario):
                if e not in expedientes:
                    expedientes.append(e)
            tipo_txt = _ws(" ".join(_lineas(td_tipo)))
            resultado, detalle = _resultado(_lineas(td_sancion))

            orden = len(out) + 1
            if expedientes:
                clave = expedientes[0]
            elif orden_del_dia:
                clave = f"OD-{orden_del_dia}"
            else:
                clave = f"#{orden}"
            if clave in claves:  # mismo expediente tratado dos veces
                clave = f"{clave}#{orden}"
            claves.add(clave)
            out.append(
                HcdnAsunto(
                    orden=orden,
                    clave=clave[:128],
                    expedientes=expedientes,
                    orden_del_dia=orden_del_dia,
                    tipo=None if _vacio(tipo_txt) else tipo_txt[:64],
                    sumario=sumario,
                    resultado=resultado,
                    detalle=detalle,
                    links=links,
                )
            )
    return out


# ───────────────────────────────────── Cliente ─────────────────────────────────────


class HcdnActividadClient:
    """Cliente secuencial a www.hcdn.gob.ar (sin ráfagas: es el sitio de la Cámara)."""

    def __init__(self, *, timeout: float = 60.0, pausa: float = 0.5) -> None:
        self._client = make_client(base_url=HCDN_BASE, timeout=timeout)
        self._pausa = pausa

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_agenda(self) -> AgendaHcdn:
        return parse_agenda(await get_text(self._client, AGENDA_PATH))

    async def fetch_sesiones_listado(self) -> tuple[list[HcdnSesionSitio], int]:
        return parse_sesiones_listado(await get_text(self._client, SESIONES_PATH))

    async def fetch_bat(self, url: str) -> list[HcdnAsunto]:
        html = await get_text(self._client, url)
        await asyncio.sleep(self._pausa)
        return parse_bat(html)
