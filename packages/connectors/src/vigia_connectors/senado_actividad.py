"""Actividad del Senado de la Nación: votaciones, agenda de comisiones, sesiones y senadores.

Complementa a `senado.py` (que trae los *papeles*, los proyectos) con lo que
*pasa* en la cámara. Nada de esto entra a `norma`: va a las tablas propias del
Congreso (migración 0012). El cruce con los proyectos es por expediente
canónico (`vigia_shared.expedientes`).

Fuentes (todas HTML server-rendered de `www.senado.gob.ar`, salvo los senadores):

- Senadores: `/micrositios/DatosAbiertos/ExportarListadoSenadores/json` (los 72
  en ejercicio) y `.../ExportarListadoSenadoresHistorico/json` (uno por período,
  desde 1854). Vienen envueltos en `{"table": {"rows": [...]}}`.
- Actas: `GET /votaciones/actas` trae el año en curso en una sola página; otros
  años con `POST` del campo `busqueda_actas[anio]` (no pide token CSRF).
- Detalle: `/votaciones/detalleActa/{id}` con totales y voto nominal.
- Agenda: `/parlamentario/comisiones/?active=agenda` (solo los próximos días).
- Sesiones: `/parlamentario/sesiones/busquedaTac` (todas, 1983→hoy, una página).

Gotchas medidos contra el sitio (2026-10-19):

- **Los ex senadores no traen ID en el acta.** El link `/senadores/senador/{ID}`
  solo aparece para quien hoy está en funciones; en un acta de 2008 ninguna fila
  lo tiene. El ID se resuelve por nombre + provincia contra el listado histórico
  (`IndiceSenadores`), que en las actas probadas cubre el 100% de las filas. Hay
  homónimos de épocas distintas (dos "MARTÍNEZ, JULIO CÉSAR" de La Rioja, 1973 y
  2017) y por eso el índice desempata por la fecha del acta.
- Los IDs de acta **no son cronológicos** (las de 2008 están entre 1624 y 2235,
  la 1 es de 2016): no sirven para inferir fechas ni completitud.
- Un ID inexistente devuelve 200 con la plantilla vacía (sin fecha): `parse_acta_detalle`
  devuelve None. Hay actas reales sin voto nominal (p.ej. la 2750, de 2009): traen
  fecha y totales en cero.
- La fecha del detalle es la **de la sesión** con la hora de la votación, así que
  una votación de madrugada (02:29) queda con la fecha del día en que arrancó la
  sesión. Sirve justamente para vincularla a su sesión por fecha.
- El día de la agenda viene **sin año** ("Martes 20 de octubre"): se infiere con la
  fecha de corrida y el día de la semana (`inferir_fecha`), que cubre el cruce de
  diciembre a enero.
"""
from __future__ import annotations

import asyncio
import hashlib
import html as htmllib
import json
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Self

import httpx
from bs4 import BeautifulSoup, NavigableString, Tag
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from vigia_connectors._http import get_text, make_client
from vigia_shared.expedientes import extraer_expedientes, normalizar_expediente

SENADO_BASE = "https://www.senado.gob.ar"

_SENADORES = "/micrositios/DatosAbiertos/ExportarListadoSenadores/json"
_SENADORES_HISTORICO = "/micrositios/DatosAbiertos/ExportarListadoSenadoresHistorico/json"
_ACTAS = "/votaciones/actas"
_DETALLE = "/votaciones/detalleActa/{id}"
_AGENDA = "/parlamentario/comisiones/?active=agenda"
_TAC = "/parlamentario/sesiones/busquedaTac"

# Argentina no tiene horario de verano desde 2009: un offset fijo evita depender
# de la base tz del sistema (en Windows no viene) para fechas que son locales.
ART = timezone(timedelta(hours=-3))

_RE_SENADOR = re.compile(r"/senadores/senador/(\d+)")
_RE_VEREXP = re.compile(r"/verExp/([^\"'\s?#]+)")
_RE_OD_LINK = re.compile(r"ordenDelDiaResultadoLink/(\d{4})/(\d+)")
_RE_OD_TEXTO = re.compile(r"O\.\s?D\.?\s*(?:N[º°o.]*\s*)?(\d{1,5})\s*/\s*(\d{4}|\d{2})\b", re.I)
_RE_FECHA_HORA = re.compile(r"(\d{2})/(\d{2})/(\d{4})\s*-\s*(\d{1,2}):(\d{2})")
_RE_HORA = re.compile(r"(\d{1,2})\s*[:.]\s*(\d{2})")
_RE_ACTA_ID = re.compile(r"/votaciones/detalleActa/(\d+)")
_RE_YOUTUBE = re.compile(r"youtube(\d+)")

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_DIAS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
_RE_DIA = re.compile(
    r"(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\s+(\d{1,2})\s+de\s+([a-záéíóú]+)",
    re.I,
)

# Valores del CHECK `ck_voto_valor` (migración 0012).
VOTOS = ("afirmativo", "negativo", "abstencion", "ausente", "presidente", "otro")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _sin_acentos(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _clave_nombre(s: str | None) -> str:
    """Forma comparable de un nombre o provincia: sin acentos, mayúsculas, sin
    puntuación salvo la coma que separa apellido de nombre."""
    t = _sin_acentos(s or "").upper()
    t = re.sub(r"[^A-Z, ]", " ", t)
    t = re.sub(r"\s*,\s*", ", ", t)
    return re.sub(r"\s+", " ", t).strip(" ,")


def _limpio(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _fecha_iso(s: str | None) -> date | None:
    try:
        return date.fromisoformat((s or "").strip()[:10])
    except ValueError:
        return None  # "Sin Datos", vacío


def _int(s: str | None) -> int | None:
    m = re.search(r"-?\d+", s or "")
    return int(m.group()) if m else None


def cargar_json_tolerante(texto: str) -> Any:
    """`json.loads` que aguanta las comas colgantes de los exports del Senado.

    Algunos exports de datos abiertos (`VersionesTac`, `BoletinNovedades`) traen
    `,}` / `,]`. Se intenta primero el JSON tal cual y solo si falla se limpian
    (la regex podría tocar una coma dentro de un string: por eso es plan B).
    """
    t = texto.lstrip("﻿")
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        return json.loads(re.sub(r",\s*([}\]])", r"\1", t))


def _filas_tabla(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        tabla = data.get("table", data)
        filas = tabla.get("rows", []) if isinstance(tabla, dict) else tabla
    else:
        filas = data
    return [f for f in (filas or []) if isinstance(f, dict)]


def _ordenes_del_dia(bloque: Tag) -> list[str]:
    """O.D. citadas en un bloque, como `699/2025`. Link primero, texto de respaldo."""
    out: list[str] = []
    for a in bloque.find_all("a", href=_RE_OD_LINK):
        anio, num = _RE_OD_LINK.search(a["href"]).groups()
        od = f"{int(num)}/{anio}"
        if od not in out:
            out.append(od)
    for num, anio in _RE_OD_TEXTO.findall(bloque.get_text(" ")):
        a4 = int(anio) + (2000 if len(anio) == 2 and int(anio) <= 50 else 1900 if len(anio) == 2 else 0)
        od = f"{int(num)}/{a4}"
        if od not in out:
            out.append(od)
    return out


def _expedientes(bloque: Tag) -> list[str]:
    """Expedientes canónicos de los links `verExp` de un bloque, más los citados en texto."""
    out: list[str] = []
    for a in bloque.find_all("a", href=_RE_VEREXP):
        exp = normalizar_expediente(_RE_VEREXP.search(a["href"]).group(1)) or normalizar_expediente(
            a.get_text(strip=True)
        )
        if exp and exp not in out:
            out.append(exp)
    for exp in extraer_expedientes(bloque.get_text(" ")):
        if exp not in out:
            out.append(exp)
    return out


def _texto_antes_de_links(bloque: Tag) -> str:
    """El texto propio de un bloque hasta el primer link (el título del acta)."""
    partes: list[str] = []
    for hijo in bloque.children:
        if isinstance(hijo, Tag):
            if hijo.name == "a" or hijo.find("a") is not None:
                break
            partes.append(hijo.get_text(" "))
        elif isinstance(hijo, NavigableString):
            partes.append(str(hijo))
    return _limpio(" ".join(partes)).rstrip(" ,")


def _etapa(s: str | None) -> str | None:
    t = _limpio(_sin_acentos(s or "")).lower()
    if not t:
        return None
    t = re.sub(r"\ben\s+", "", t)
    return t  # "general", "particular", "general y particular"...


def _resultado(s: str | None) -> str | None:
    t = _limpio(_sin_acentos(s or "")).lower()
    return t or None  # "afirmativo", "negativo"...


def mapear_voto(s: str | None) -> str:
    """Texto de la columna "¿Cómo votó?" → valor del CHECK de `voto.voto`."""
    t = _sin_acentos(s or "").upper()
    if "AFIRMATIV" in t:
        return "afirmativo"
    if "NEGATIV" in t:
        return "negativo"
    if "ABSTEN" in t:
        return "abstencion"
    if "AUSENTE" in t:
        return "ausente"
    if "PRESIDE" in t:
        return "presidente"
    return "otro"


# ---------------------------------------------------------------------------
# senadores
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Senador:
    """Una fila de un export de senadores. En el histórico hay una por período."""

    external_id: str
    nombre: str                 # "APELLIDO, NOMBRE", como en las actas
    distrito: str | None
    bloque: str | None
    partido: str | None
    mandato_desde: date | None
    mandato_hasta: date | None
    raw: dict[str, Any] = field(default_factory=dict)


def parse_senadores_json(texto: str) -> list[Senador]:
    """Export de senadores en ejercicio (`ExportarListadoSenadores/json`)."""
    out: list[Senador] = []
    for f in _filas_tabla(cargar_json_tolerante(texto)):
        sid = str(f.get("ID") or "").strip()
        if not sid:
            continue
        apellido = _limpio(f.get("APELLIDO"))
        nombre = _limpio(f.get("NOMBRE"))
        out.append(Senador(
            external_id=sid,
            nombre=f"{apellido}, {nombre}" if nombre else apellido,
            distrito=_limpio(f.get("PROVINCIA")) or None,
            bloque=_limpio(f.get("BLOQUE")) or None,
            partido=_limpio(f.get("PARTIDO O ALIANZA")) or None,
            mandato_desde=_fecha_iso(f.get("D_LEGAL")) or _fecha_iso(f.get("D_REAL")),
            mandato_hasta=_fecha_iso(f.get("C_LEGAL")) or _fecha_iso(f.get("C_REAL")),
            raw=f,
        ))
    return out


def parse_senadores_historico_json(texto: str) -> list[Senador]:
    """Export histórico (`ExportarListadoSenadoresHistorico/json`): una fila por período.

    No trae bloque (solo partido o alianza). El mandato es el período *real*
    (el legal es el teórico: una renuncia o un reemplazo lo acortan).
    """
    out: list[Senador] = []
    for f in _filas_tabla(cargar_json_tolerante(texto)):
        sid = str(f.get("ID") or "").strip()
        if not sid:
            continue
        out.append(Senador(
            external_id=sid,
            nombre=_limpio(f.get("SENADOR")),
            distrito=_limpio(f.get("PROVINCIA")) or None,
            bloque=None,
            partido=_limpio(f.get("PARTIDO POLITICO O ALIANZA")) or None,
            mandato_desde=_fecha_iso(f.get("INICIO PERIODO REAL")) or _fecha_iso(f.get("INICIO PERIODO LEGAL")),
            mandato_hasta=_fecha_iso(f.get("CESE PERIODO REAL")) or _fecha_iso(f.get("CESE PERIODO LEGAL")),
            raw=f,
        ))
    return out


def id_sintetico(nombre: str, distrito: str | None) -> str:
    """ID estable para un senador que no aparece en ningún export.

    Prefijo `nom-` para que se distinga a simple vista de un ID real del Senado
    (que es numérico) y nunca choque con uno.
    """
    clave = f"{_clave_nombre(nombre)}|{_clave_nombre(distrito)}"
    return "nom-" + hashlib.sha1(clave.encode()).hexdigest()[:16]


class IndiceSenadores:
    """Resuelve (nombre, provincia, fecha) → ID del Senado para las filas sin link.

    Se arma con los períodos del export histórico más los en ejercicio. Si hay
    homónimos en la misma provincia gana el que estaba en funciones en la fecha
    del acta (con margen: los cortes de mandato no coinciden exacto con las sesiones).
    """

    def __init__(self, senadores: Iterable[Senador]) -> None:
        self._por_clave: dict[tuple[str, str], list[Senador]] = {}
        self._por_nombre: dict[str, set[str]] = {}
        for s in senadores:
            k = (_clave_nombre(s.nombre), _clave_nombre(s.distrito))
            self._por_clave.setdefault(k, []).append(s)
            self._por_nombre.setdefault(k[0], set()).add(s.external_id)

    def __len__(self) -> int:
        return len(self._por_clave)

    def resolver(self, nombre: str, distrito: str | None, fecha: date | None = None) -> str | None:
        periodos = self._por_clave.get((_clave_nombre(nombre), _clave_nombre(distrito)))
        if not periodos:
            # Provincia escrita distinto: sirve el nombre solo si no es ambiguo.
            ids = self._por_nombre.get(_clave_nombre(nombre), set())
            return next(iter(ids)) if len(ids) == 1 else None
        ids = {p.external_id for p in periodos}
        if len(ids) == 1 or fecha is None:
            return min(ids) if len(ids) > 1 else next(iter(ids))

        def distancia(p: Senador) -> int:
            desde = p.mandato_desde or date.min
            hasta = p.mandato_hasta or date.max
            if desde - timedelta(days=60) <= fecha <= hasta + timedelta(days=60):
                return 0
            return min(abs((fecha - desde).days), abs((fecha - hasta).days))

        return min(periodos, key=lambda p: (distancia(p), p.external_id)).external_id


# ---------------------------------------------------------------------------
# actas de votación
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ActaListado:
    """Una fila de `/votaciones/actas`."""

    acta_id: str
    fecha: date
    numero_acta: str | None
    titulo: str
    etapa: str | None
    resultado: str | None
    mayoria: str | None
    expedientes: list[str]
    ordenes_del_dia: list[str]
    url_pdf: str | None
    video_url: str | None

    @property
    def url(self) -> str:
        return SENADO_BASE + _DETALLE.format(id=self.acta_id)


@dataclass(slots=True)
class VotoNominal:
    senador_id: str | None      # None si la fila no trae link (ex senadores)
    nombre: str
    bloque: str | None
    distrito: str | None
    voto: str                   # uno de VOTOS
    voto_texto: str             # tal cual lo publica el Senado


@dataclass(slots=True)
class ActaDetalle:
    """`/votaciones/detalleActa/{id}`."""

    acta_id: str
    fecha: datetime             # fecha de la sesión + hora de la votación, ART
    numero_acta: str | None
    titulo: str
    etapa: str | None
    resultado: str | None
    mayoria: str | None
    afirmativos: int | None
    negativos: int | None
    abstenciones: int | None
    ausentes: int | None
    expedientes: list[str]
    ordenes_del_dia: list[str]
    votos: list[VotoNominal]


def parse_actas_listado(html: str) -> list[ActaListado]:
    """Tabla `#actasTable` del listado anual de actas."""
    soup = BeautifulSoup(html, "html.parser")
    tabla = soup.find("table", id="actasTable")
    if tabla is None:
        return []
    out: list[ActaListado] = []
    for tr in tabla.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 8:
            continue
        link = tr.find("a", href=_RE_ACTA_ID)
        if link is None:
            continue
        acta_id = _RE_ACTA_ID.search(link["href"]).group(1)

        oculto = tds[0].find("span")
        stamp = re.sub(r"\D", "", oculto.get_text()) if oculto else ""
        try:
            fecha = date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))
        except ValueError:
            m = re.search(r"(\d{2})/(\d{2})/(\d{4})", tds[0].get_text())
            if not m:
                continue
            fecha = date(int(m[3]), int(m[2]), int(m[1]))

        celda = tds[2]
        pdf = tr.find("a", href=re.compile(r"verActaVotacion/"))
        video = tr.find("a", class_=_RE_YOUTUBE)
        resultado = tds[4].find("div") or tds[4]
        out.append(ActaListado(
            acta_id=acta_id,
            fecha=fecha,
            numero_acta=_limpio(tds[1].get_text()) or None,
            titulo=_texto_antes_de_links(celda),
            etapa=_etapa(tds[3].get_text()),
            resultado=_resultado(resultado.get_text()),
            mayoria=_limpio(tds[6].get_text()) or None,
            expedientes=_expedientes(celda),
            ordenes_del_dia=_ordenes_del_dia(celda),
            url_pdf=(SENADO_BASE + pdf["href"]) if pdf else None,
            video_url=(video.get("href") or None) if video else None,
        ))
    return out


def parse_acta_detalle(html: str, acta_id: str | int) -> ActaDetalle | None:
    """Detalle con totales y voto nominal. None si el acta no existe (plantilla vacía)."""
    soup = BeautifulSoup(html, "html.parser")
    p_acta = soup.find("p", string=re.compile(r"Acta\s+Nro", re.I))
    if p_acta is None:
        return None
    cabecera = p_acta.find_parent("div", class_="row") or p_acta.parent
    m = _RE_FECHA_HORA.search(cabecera.get_text(" "))
    if m is None:
        return None
    d, mn, y, hh, mi = (int(x) for x in m.groups())
    fecha = datetime(y, mn, d, hh, mi, tzinfo=ART)

    p_titulo = p_acta.find_next_sibling("p")
    titulo = _texto_antes_de_links(p_titulo) if p_titulo else ""

    # Columna izquierda: dos <SPAN> sueltos, fecha y mayoría requerida.
    spans = [_limpio(s.get_text()) for s in p_acta.parent.find_all("span")]
    mayoria = next((s for s in spans if s and not _RE_FECHA_HORA.search(s)), None)

    # Columna derecha: resultado y etapa en <li><p>, totales en pares h3 (número) / h4 (rótulo).
    lis = [_limpio(li.get_text()) for li in cabecera.find_all("li")]
    totales: dict[str, int | None] = {}
    for h4 in cabecera.find_all("h4"):
        rotulo = _sin_acentos(_limpio(h4.get_text())).upper()
        h3 = h4.find_previous_sibling("h3")
        totales[rotulo] = _int(h3.get_text()) if h3 else None

    votos: list[VotoNominal] = []
    tabla = soup.find("table", id="tabla")
    for tr in (tabla.find_all("tr") if tabla else []):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        link = tr.find("a", href=_RE_SENADOR)
        texto_voto = _limpio(tds[4].get_text())
        votos.append(VotoNominal(
            senador_id=_RE_SENADOR.search(link["href"]).group(1) if link else None,
            nombre=_limpio(tds[1].get_text()),
            bloque=_limpio(tds[2].get_text()) or None,
            distrito=_limpio(tds[3].get_text()) or None,
            voto=mapear_voto(texto_voto),
            voto_texto=texto_voto,
        ))

    return ActaDetalle(
        acta_id=str(acta_id),
        fecha=fecha,
        numero_acta=(re.sub(r"(?i).*acta\s+nro\s*:?", "", _limpio(p_acta.get_text())).strip() or None),
        titulo=titulo,
        etapa=_etapa(lis[1]) if len(lis) > 1 else None,
        resultado=_resultado(lis[0]) if lis else None,
        mayoria=mayoria,
        afirmativos=totales.get("AFIRMATIVOS"),
        negativos=totales.get("NEGATIVOS"),
        abstenciones=totales.get("ABSTENCIONES"),
        ausentes=totales.get("AUSENTES"),
        expedientes=_expedientes(p_titulo) if p_titulo else [],
        ordenes_del_dia=_ordenes_del_dia(p_titulo) if p_titulo else [],
        votos=votos,
    )


# ---------------------------------------------------------------------------
# agenda de comisiones
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ReunionAgenda:
    external_id: str
    fecha_hora: datetime        # ART
    comision: str
    sala: str | None
    tipo: str | None            # "comisiones" | "asesores" (el grupo de la página)
    temario: str | None         # texto plano, con saltos de línea
    expedientes: list[str]
    raw: dict[str, Any] = field(default_factory=dict)


def inferir_fecha(dia_semana: str, dia: int, mes: int, hoy: date) -> date | None:
    """La agenda dice "Martes 20 de octubre", sin año.

    Entre los años vecinos al de corrida gana el que hace coincidir el día de la
    semana; si empatan (o no coincide ninguno), el más cercano a `hoy`. Así un
    "Martes 5 de enero" visto el 28 de diciembre cae en el año siguiente.
    """
    nombre = _sin_acentos(dia_semana).lower()
    candidatos: list[date] = []
    for y in (hoy.year - 1, hoy.year, hoy.year + 1):
        try:
            candidatos.append(date(y, mes, dia))
        except ValueError:
            continue
    if not candidatos:
        return None
    return min(
        candidatos,
        key=lambda c: (_DIAS[c.weekday()] != nombre, abs((c - hoy).days)),
    )


_BLOQUES = ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table")


def _texto_bloques(soup: BeautifulSoup) -> str:
    """Texto plano respetando párrafos: salto de línea solo entre bloques, nada
    entre tags inline (un `<strong>` o un `<a>` en medio de una palabra la cortaría)."""
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup.find_all(_BLOQUES):
        tag.insert_after("\n")
    lineas = (_limpio(x) for x in soup.get_text("").split("\n"))
    return "\n".join(x for x in lineas if x)


def _id_reunion(fecha_hora: datetime, comision: str) -> str:
    clave = f"S|{fecha_hora.isoformat()}|{_clave_nombre(comision)}"
    return hashlib.sha1(clave.encode()).hexdigest()[:32]


def parse_agenda(html: str, hoy: date) -> list[ReunionAgenda]:
    """Filas `div.sgr-reunion-row` bajo su header de día y su grupo
    ("REUNIONES DE COMISIONES" / "REUNIONES DE ASESORES")."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[ReunionAgenda] = []
    grupo: str | None = None
    dia_texto: str | None = None
    fecha: date | None = None
    for el in soup.find_all("div"):
        clases = el.get("class") or []
        if "sgr-group-title" in clases:
            t = _limpio(el.get_text()).lower()
            grupo = re.sub(r"^reuniones\s+de\s+", "", t) or None
            continue
        if not clases:
            texto = _limpio(el.get_text(" "))
            m = _RE_DIA.fullmatch(texto)
            if m and el.find_parent(class_="sgr-reunion-row") is None:
                mes = _MESES.get(_sin_acentos(m[3]).lower())
                dia_texto = texto
                fecha = inferir_fecha(m[1], int(m[2]), mes, hoy) if mes else None
            continue
        if "sgr-reunion-row" not in clases or fecha is None:
            continue

        def col(nombre: str, fila: Tag = el) -> str:
            c = fila.find(class_=nombre)
            return _limpio(c.get_text(" ")) if c else ""

        comision = col("sgr-col-commission")
        if not comision:
            continue
        hora_texto = col("sgr-col-time")
        mh = _RE_HORA.search(hora_texto)
        hh, mi = (int(mh[1]), int(mh[2])) if mh else (0, 0)
        fecha_hora = datetime(fecha.year, fecha.month, fecha.day, hh, mi, tzinfo=ART)

        temario: str | None = None
        expedientes: list[str] = []
        area = el.find("textarea", id=re.compile(r"^temario-content-"))
        if area is not None:
            # El temario viene como HTML escapado adentro del textarea.
            interno = BeautifulSoup(htmllib.unescape(area.decode_contents()), "html.parser")
            # Los links `verExp` del temario van primero (`_expedientes`): el texto
            # a veces parte el expediente entre dos tags ("S-285/2" + "5").
            expedientes = _expedientes(interno)
            temario = _texto_bloques(interno) or None
        titulo_meta = el.find(class_="temario-reunion-title")

        out.append(ReunionAgenda(
            external_id=_id_reunion(fecha_hora, comision),
            fecha_hora=fecha_hora,
            comision=comision,
            sala=col("sgr-col-place") or None,
            tipo=grupo,
            temario=temario,
            expedientes=expedientes,
            raw={
                "dia": dia_texto,
                "hora": hora_texto,
                "grupo": grupo,
                "titulo": _limpio(titulo_meta.get_text()) if titulo_meta else None,
                "temario_id": area.get("id") if area is not None else None,
            },
        ))
    return out


# ---------------------------------------------------------------------------
# sesiones (versiones taquigráficas)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SesionTac:
    fecha: date
    tipo: str | None
    numero_sesion: int | None
    reunion: int | None
    url_taquigrafica: str | None
    url_diario: str | None

    @property
    def external_id(self) -> str:
        # (fecha, reunión) es único en las 1818 filas de 1983 a 2026.
        r = "" if self.reunion is None else str(self.reunion)
        return f"{self.fecha.isoformat()}/{r}"


def parse_sesiones_tac(html: str) -> list[SesionTac]:
    """Tabla `#tablaTaquigrafos`: Fecha | Tipo | Nº Sesión | Nº Reunión | Taquigráfica | Diario.

    Son ~1800 filas; ~820 tienen versión taquigráfica y casi todas diario.
    """
    soup = BeautifulSoup(html, "html.parser")
    tabla = soup.find("table", id="tablaTaquigrafos")
    if tabla is None:
        return []
    out: list[SesionTac] = []
    for tr in tabla.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        m = re.search(r"(\d{2})-(\d{2})-(\d{4})", tds[0].get_text())
        if not m:
            continue
        try:
            fecha = date(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            continue
        tac = tr.find("a", href=re.compile(r"/downloadTac$"))
        diario = tr.find("a", href=re.compile(r"/descargarDiario$"))
        out.append(SesionTac(
            fecha=fecha,
            tipo=_limpio(tds[1].get_text()) or None,
            numero_sesion=_int(tds[2].get_text()),
            reunion=_int(tds[3].get_text()),
            url_taquigrafica=(SENADO_BASE + tac["href"]) if tac else None,
            url_diario=(SENADO_BASE + diario["href"]) if diario else None,
        ))
    return out


# ---------------------------------------------------------------------------
# cliente
# ---------------------------------------------------------------------------

class SenadoActividadClient:
    """Cliente async. Mismo patrón que `SenadoClient`: concurrencia acotada y un
    detalle que falla no tumba la corrida."""

    def __init__(self, *, timeout: float = 60.0, concurrency: int = 4) -> None:
        self._client = make_client(
            base_url=SENADO_BASE,
            timeout=timeout,
            headers={"User-Agent": "vigia/0.1 (+https://vigia.openarg.org)"},
        )
        self._sem = asyncio.Semaphore(concurrency)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post_text(self, path: str, data: dict[str, str]) -> str:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=0.5, max=4),
            retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
            reraise=True,
        ):
            with attempt:
                r = await self._client.post(path, data=data)
                r.raise_for_status()
                return r.text
        raise RuntimeError("unreachable")

    async def fetch_senadores(self) -> list[Senador]:
        return parse_senadores_json(await get_text(self._client, _SENADORES))

    async def fetch_senadores_historico(self) -> list[Senador]:
        return parse_senadores_historico_json(await get_text(self._client, _SENADORES_HISTORICO))

    async def fetch_actas(self, anio: int | None = None) -> list[ActaListado]:
        """Actas de un año. Sin año, el GET trae el año en curso."""
        if anio is None:
            return parse_actas_listado(await get_text(self._client, _ACTAS))
        html = await self._post_text(_ACTAS, {"busqueda_actas[anio]": str(anio), "busqueda_actas[titulo]": ""})
        return parse_actas_listado(html)

    async def fetch_acta_detalle(self, acta_id: str | int) -> ActaDetalle | None:
        async with self._sem:
            html = await get_text(self._client, _DETALLE.format(id=acta_id))
        return parse_acta_detalle(html, acta_id)

    async def fetch_detalles(
        self, acta_ids: Iterable[str]
    ) -> tuple[dict[str, ActaDetalle | None], list[str]]:
        """Detalles en paralelo acotado. Devuelve (detalles, ids que fallaron).

        Un detalle que falla (el sitio es lento y a veces corta) no aborta el
        resto: el acta queda afuera de esta corrida y la próxima lo reintenta.
        """
        ids = list(acta_ids)
        res = await asyncio.gather(*(self.fetch_acta_detalle(i) for i in ids), return_exceptions=True)
        ok: dict[str, ActaDetalle | None] = {}
        fallidos: list[str] = []
        for i, r in zip(ids, res, strict=True):
            if isinstance(r, BaseException):
                fallidos.append(i)
            else:
                ok[i] = r
        return ok, fallidos

    async def fetch_agenda(self, hoy: date | None = None) -> list[ReunionAgenda]:
        return parse_agenda(await get_text(self._client, _AGENDA), hoy or datetime.now(ART).date())

    async def fetch_sesiones(self) -> list[SesionTac]:
        return parse_sesiones_tac(await get_text(self._client, _TAC))
