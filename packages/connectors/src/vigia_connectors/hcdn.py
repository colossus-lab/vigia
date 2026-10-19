"""HCDN — proyectos parlamentarios (datos.hcdn.gob.ar, CKAN).

La Cámara de Diputados publica el dataset `proyectos-parlamentarios` con todos
los proyectos presentados (ley, resolución, declaración...), actualizado a
diario. Lo usamos como fuente del tipo `PROYECTO` del feed de Vigía.

La URL del recurso CSV cambia de nombre con cada versión (2.0, 2.2, ...), así
que se resuelve en runtime vía la API CKAN (`package_show`).

Columnas del CSV:
PROYECTO_ID, TITULO, PUBLICACION_FECHA, PUBLICACION_ID, CAMARA_ORIGEN,
EXP_DIPUTADOS, EXP_SENADO, TIPO, AUTOR

Para la sección Congreso se leen además `legisladores` y `sesiones` (ver
`iter_mandatos_csv`, `iter_composicion_csv` e `iter_sesiones_csv`).
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime
from pathlib import Path
from typing import Self

from vigia_connectors._http import get_json, make_client
from vigia_connectors.sectores import detect_sector

CKAN_BASE = "https://datos.hcdn.gob.ar"
PACKAGE_ID = "proyectos-parlamentarios"
MOVIMIENTOS_PACKAGE_ID = "movimientos-de-proyectos"
LEGISLADORES_PACKAGE_ID = "legisladores"
SESIONES_PACKAGE_ID = "sesiones"

# El package `legisladores` trae dos CSV y ninguno alcanza solo:
# - "Composición Actual de la Cámara" (257 filas) es la nómina vigente con los
#   nombres bien escritos, pero NO trae el ID del diputado.
# - "Diputados" es el histórico de mandatos (una fila por mandato y por bloque)
#   y sí trae el ID (`HCDN1136`), pero en mayúsculas y sin tildes.
# Se bajan los dos y se cruzan (`legisladores_vigentes`).
RECURSO_COMPOSICION = "Composición Actual"
RECURSO_MANDATOS = "Diputados"

# Derivación de estado de tramitación desde los textos libres de movimientos.
# Sin fechas confiables (mayoría NA) se toma el estado de mayor rango visto.
# "CONSIDERACION Y APROBACION" en cámara de origen suele preceder a un
# "PASA A SENADO/DIPUTADOS" (que rankea más alto y gana cuando existe).
_ESTADO_RULES: list[tuple[int, str, tuple[str, ...]]] = [
    (6, "Sancionado", ("SANCIONADO", "SANCION DEFINITIVA", "COMUNICACION AL PODER EJECUTIVO")),
    (5, "Media sanción", ("PASA A SENADO", "PASA A DIPUTADOS", "MEDIA SANCION")),
    (4, "Aprobado", ("CONSIDERACION Y APROBACION", "APROBACION ARTICULO 114", "APROBADO")),
    (3, "Con dictamen", ("DICTAMEN",)),
    (2, "Archivado", ("PASA AL ARCHIVO", "AL ARCHIVO")),
    (1, "En comisión", ("GIRO A", "AMPLIACION DE GIRO", "CAMBIO DE GIRO")),
]


def clasificar_movimiento(texto: str | None) -> tuple[int, str] | None:
    """(rank, estado) que implica un movimiento, o None si no cambia el estado."""
    t = (texto or "").upper()
    if not t:
        return None
    for rank, estado, keywords in _ESTADO_RULES:
        for kw in keywords:
            if kw in t:
                return rank, estado
    return None


def derivar_estado(movimientos: list[str | None]) -> str | None:
    """Estado de tramitación derivado del conjunto de movimientos de un proyecto."""
    best: tuple[int, str] | None = None
    for texto in movimientos:
        c = clasificar_movimiento(texto)
        if c is not None and (best is None or c[0] > best[0]):
            best = c
    return best[1] if best else None


@dataclass(slots=True)
class HcdnProyecto:
    proyecto_id: str
    titulo: str
    fecha_publicacion: Date | None
    camara_origen: str | None
    exp_diputados: str | None
    exp_senado: str | None
    tipo_proyecto: str | None  # LEY | RESOLUCION | DECLARACION | ...
    autor: str | None

    @property
    def expediente(self) -> str | None:
        return self.exp_diputados or self.exp_senado

    def organismo(self) -> str:
        if (self.camara_origen or "").strip().lower().startswith("senado"):
            return "Honorable Senado de la Nación"
        return "Honorable Cámara de Diputados de la Nación"

    def detect_sector(self) -> str | None:
        return detect_sector(self.titulo)


@dataclass(slots=True)
class HcdnMovimiento:
    proyecto_id: str  # == norma.external_id (fuente hcdn_proyectos)
    movimiento: str
    fecha: Date | None
    orden: str | None


def _parse_fecha(value: str | None) -> Date | None:
    value = (value or "").strip()
    if not value or value.upper() == "NA":
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "")).date()
    except ValueError:
        return None


def _na(value: str | None) -> str | None:
    v = (value or "").strip()
    return None if not v or v.upper() == "NA" else v


def _norm(value: str | None) -> str:
    """Mayúsculas, sin tildes ni puntuación: para cruzar nombres entre CSVs."""
    t = unicodedata.normalize("NFKD", value or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).upper()
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", t).split())


def elegir_recurso_csv(resources: list[dict], recurso: str | None = None) -> str | None:
    """URL del recurso CSV de un package. Sin `recurso`, el primer CSV (lo de siempre).

    Con `recurso` gana el nombre exacto y, si no hay, el que empieza así
    ("Composición Actual" → "Composición Actual de la Cámara"), sin importar
    tildes ni mayúsculas.
    """
    csvs = [r for r in resources if (r.get("format") or "").upper() == "CSV"]
    if recurso is None:
        return csvs[0]["url"] if csvs else None
    buscado = _norm(recurso)
    for r in csvs:
        if _norm(r.get("name")) == buscado:
            return r["url"]
    for r in csvs:
        if _norm(r.get("name")).startswith(buscado):
            return r["url"]
    return None


def _parse_fecha_dmy(value: str | None) -> Date | None:
    """`03/12/2025` → date (formato de la Composición Actual)."""
    try:
        return datetime.strptime((value or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _parse_dt(value: str | None) -> datetime | None:
    v = (value or "").strip()
    if not v or v.upper() == "NA":
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", ""))
    except ValueError:
        return None


@dataclass(slots=True)
class HcdnMandato:
    """Una fila del histórico `Diputados`: un mandato con UN bloque (si cambió
    de bloque a mitad de mandato hay varias filas con el mismo ID)."""

    diputado_id: str  # HCDN1136
    apellido: str
    nombre: str
    genero: str | None
    distrito: str | None
    inicio: Date | None
    fin: Date | None
    juramento: Date | None
    cese: Date | None
    bloque: str | None
    bloque_inicio: Date | None
    bloque_fin: Date | None

    def vigente(self, hoy: Date) -> bool:
        if self.inicio is None or self.fin is None or not (self.inicio <= hoy <= self.fin):
            return False
        # CESE anterior a FIN = renuncia, licencia larga, fallecimiento.
        return self.cese is None or self.cese >= hoy


@dataclass(slots=True)
class HcdnDiputadoActual:
    """Una fila de la Composición Actual (sin ID: se cruza con los mandatos)."""

    apellido: str
    nombre: str
    sexo: str | None
    distrito: str | None
    mandato: str | None  # "2025-2029"
    jura: Date | None
    inicio: Date | None
    bloque: str | None


@dataclass(slots=True)
class HcdnLegislador:
    external_id: str  # el ID del histórico (HCDN1136)
    nombre: str  # "Apellido, Nombre"
    bloque: str | None
    distrito: str | None
    mandato_desde: Date | None
    mandato_hasta: Date | None
    raw: dict


def legisladores_vigentes(
    mandatos: Iterable[HcdnMandato], actuales: Iterable[HcdnDiputadoActual], hoy: Date
) -> tuple[list[HcdnLegislador], list[HcdnDiputadoActual]]:
    """Cruza la Composición Actual con el histórico de mandatos para darle ID a
    cada diputado en funciones. Devuelve `(legisladores, sin_id)`.

    La llave es apellido + distrito normalizados. Si hay más de un candidato
    (hoy hay dos García por Buenos Aires) desempata el nombre completo y, si
    no alcanza, el primer nombre. Solo cuentan los mandatos vigentes hoy: un
    homónimo de otro período no puede quedarse con el ID.
    """
    por_id: dict[str, list[HcdnMandato]] = defaultdict(list)
    for m in mandatos:
        por_id[m.diputado_id].append(m)

    # La llave sale del mandato VIGENTE: el distrito cambia entre mandatos
    # (Bregman fue por Buenos Aires en 2013 y hoy es por CABA).
    vigentes: dict[tuple[str, str], list[str]] = defaultdict(list)
    for did, filas in por_id.items():
        vig = next((f for f in filas if f.vigente(hoy)), None)
        if vig is not None:
            vigentes[(_norm(vig.apellido), _norm(vig.distrito))].append(did)

    out: list[HcdnLegislador] = []
    sin_id: list[HcdnDiputadoActual] = []
    usados: set[str] = set()
    for a in actuales:
        clave = (_norm(a.apellido), _norm(a.distrito))
        candidatos = [c for c in vigentes.get(clave, []) if c not in usados]
        if len(candidatos) > 1:
            nom = _norm(a.nombre)
            elegidos = [c for c in candidatos if _norm(por_id[c][0].nombre) == nom]
            if not elegidos and nom:
                primero = nom.split()[0]
                elegidos = [c for c in candidatos if _norm(por_id[c][0].nombre).split()[:1] == [primero]]
            candidatos = elegidos
        if len(candidatos) != 1:
            sin_id.append(a)
            continue
        did = candidatos[0]
        usados.add(did)
        filas = sorted(por_id[did], key=lambda f: (f.inicio or Date.min, f.bloque_inicio or Date.min))
        en_curso = [f for f in filas if f.vigente(hoy)]
        mandato = en_curso[-1] if en_curso else filas[-1]
        out.append(
            HcdnLegislador(
                external_id=did,
                nombre=f"{a.apellido}, {a.nombre}" if a.nombre else a.apellido,
                # El bloque de la Composición Actual es el de hoy; el histórico
                # puede venir atrasado en un cambio de bloque reciente.
                bloque=a.bloque or mandato.bloque,
                distrito=a.distrito or mandato.distrito,
                mandato_desde=mandato.inicio,
                mandato_hasta=mandato.fin,
                raw={
                    "id": did,
                    "sexo": a.sexo,
                    "mandato": a.mandato,
                    "jura": a.jura.isoformat() if a.jura else None,
                    "cese": mandato.cese.isoformat() if mandato.cese else None,
                    # Bloques del mandato vigente, en orden: el bloque cambia.
                    "bloques": [
                        {
                            "bloque": f.bloque,
                            "desde": f.bloque_inicio.isoformat() if f.bloque_inicio else None,
                            "hasta": f.bloque_fin.isoformat() if f.bloque_fin else None,
                        }
                        for f in filas
                        if f.inicio == mandato.inicio
                    ],
                },
            )
        )
    return out, sin_id


_RE_PERIODO_ID = re.compile(r"HCDN(?P<periodo>\d{3})(?P<letra>[RA])(?P<reunion>\d+)")


@dataclass(slots=True)
class HcdnSesionCsv:
    """Una fila del dataset `sesiones` (2008→).

    Ojo: REUNION_INICIO/FIN vienen corridas 2 días para atrás respecto del
    sitio y del Boletín de Asuntos Tratados (408 de 408 filas, medido el
    2026-10-19). Se corrige al combinar con el listado (`combinar_sesiones`).
    """

    periodo: int
    asamblea: bool  # PERIODO_ID con "A" (Asamblea Legislativa) en vez de "R"
    reunion: int
    reunion_tipo: str | None
    sesion_no: int | None  # 0 en el CSV (minoría, preparatoria, asamblea) → None
    inicio: datetime | None
    fin: datetime | None
    camara: str | None  # DIPUTADOS | ASAMBLEA
    periodo_id: str


class HcdnClient:
    def __init__(self, *, timeout: float = 300.0) -> None:
        self._client = make_client(base_url=CKAN_BASE, timeout=timeout)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def resolve_csv_url(self, package_id: str = PACKAGE_ID, recurso: str | None = None) -> str:
        """Resuelve la URL vigente del recurso CSV de un package vía package_show.

        Las URLs de recursos cambian de nombre con cada versión (2.0, 3.5, ...),
        por eso siempre se resuelven en runtime. Con `recurso` se elige por
        nombre entre varios CSV del mismo package (ver `elegir_recurso_csv`).
        """
        data = await get_json(self._client, f"/api/3/action/package_show?id={package_id}")
        url = elegir_recurso_csv(data["result"]["resources"], recurso)
        if url is None:
            detalle = f" '{recurso}'" if recurso else ""
            raise ValueError(f"No CSV resource{detalle} in CKAN package {package_id}")
        return url

    async def download_csv(
        self, dest: Path, package_id: str = PACKAGE_ID, recurso: str | None = None
    ) -> Path:
        """Stream del CSV completo de un package a disco."""
        url = await self.resolve_csv_url(package_id, recurso)
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with self._client.stream("GET", url) as resp:
            resp.raise_for_status()
            with dest.open("wb") as fh:
                async for chunk in resp.aiter_bytes(chunk_size=1024 * 256):
                    if chunk:
                        fh.write(chunk)
        return dest

    @staticmethod
    def iter_csv(csv_path: Path) -> Iterator[HcdnProyecto]:
        """Itera proyectos de a uno desde el CSV en disco (memory-friendly)."""
        with csv_path.open("rb") as binary:
            text = io.TextIOWrapper(binary, encoding="utf-8-sig", errors="replace", newline="")
            reader = csv.DictReader(text)
            for row in reader:
                p = HcdnClient._row_to_proyecto(row)
                if p is not None:
                    yield p

    @staticmethod
    def iter_movimientos_csv(csv_path: Path) -> Iterator["HcdnMovimiento"]:
        """Itera movimientos desde el CSV en disco (PROYECTO_ID, FECHA, MOVIMIENTO, ORDEN)."""
        with csv_path.open("rb") as binary:
            text = io.TextIOWrapper(binary, encoding="utf-8-sig", errors="replace", newline="")
            reader = csv.DictReader(text)
            for row in reader:
                pid = (row.get("PROYECTO_ID") or "").strip()
                mov = _na(row.get("MOVIMIENTO"))
                if not pid or not mov:
                    continue  # la mayoría de las filas son NA (proyectos sin movimientos)
                yield HcdnMovimiento(
                    proyecto_id=pid,
                    movimiento=mov,
                    fecha=_parse_fecha(row.get("FECHA")),
                    orden=_na(row.get("ORDEN")),
                )

    @staticmethod
    def _dict_rows(csv_path: Path) -> Iterator[dict]:
        with csv_path.open("rb") as binary:
            text = io.TextIOWrapper(binary, encoding="utf-8-sig", errors="replace", newline="")
            yield from csv.DictReader(text)

    @staticmethod
    def iter_mandatos_csv(csv_path: Path) -> Iterator[HcdnMandato]:
        """Histórico `Diputados`: ID, APELLIDO, NOMBRE, GENERO, DISTRITO, INICIO,
        FIN, JURAMENTO, CESE, BLOQUE, BLOQUE_INICIO, BLOQUE_FIN."""
        for row in HcdnClient._dict_rows(csv_path):
            did = (row.get("ID") or "").strip()
            apellido = (row.get("APELLIDO") or "").strip()
            if not did or not apellido:
                continue
            yield HcdnMandato(
                diputado_id=did,
                apellido=apellido,
                nombre=(row.get("NOMBRE") or "").strip(),
                genero=_na(row.get("GENERO")),
                distrito=_na(row.get("DISTRITO")),
                inicio=_parse_fecha(row.get("INICIO")),
                fin=_parse_fecha(row.get("FIN")),
                juramento=_parse_fecha(row.get("JURAMENTO")),
                cese=_parse_fecha(row.get("CESE")),
                bloque=_na(row.get("BLOQUE")),
                bloque_inicio=_parse_fecha(row.get("BLOQUE_INICIO")),
                bloque_fin=_parse_fecha(row.get("BLOQUE_FIN")),
            )

    @staticmethod
    def iter_composicion_csv(csv_path: Path) -> Iterator[HcdnDiputadoActual]:
        """Composición Actual: APELLIDO, NOMBRE, SEXO, DISTRITO, MANDATO,
        FECHA_DE_JURA, FECHA_DE_INICIO, BLOQUE (fechas dd/mm/aaaa)."""
        for row in HcdnClient._dict_rows(csv_path):
            apellido = (row.get("APELLIDO") or "").strip()
            if not apellido:
                continue
            yield HcdnDiputadoActual(
                apellido=apellido,
                nombre=(row.get("NOMBRE") or "").strip(),
                sexo=_na(row.get("SEXO")),
                distrito=_na(row.get("DISTRITO")),
                mandato=_na(row.get("MANDATO")),
                jura=_parse_fecha_dmy(row.get("FECHA_DE_JURA")),
                inicio=_parse_fecha_dmy(row.get("FECHA_DE_INICIO")),
                bloque=_na(row.get("BLOQUE")),
            )

    @staticmethod
    def iter_sesiones_csv(csv_path: Path) -> Iterator[HcdnSesionCsv]:
        """`sesiones`: REUNION_NO, REUNION_TIPO, SESION_NO, REUNION_INICIO,
        REUNION_FIN, SESION_CAMARA, PERIODO_ID (`HCDN144R07`)."""
        for row in HcdnClient._dict_rows(csv_path):
            pid = (row.get("PERIODO_ID") or "").strip()
            m = _RE_PERIODO_ID.fullmatch(pid)
            if not m:
                continue
            sesion_no = (row.get("SESION_NO") or "").strip()
            yield HcdnSesionCsv(
                periodo=int(m["periodo"]),
                asamblea=m["letra"] == "A",
                reunion=int(m["reunion"]),
                reunion_tipo=_na(row.get("REUNION_TIPO")),
                sesion_no=int(sesion_no) if sesion_no.isdigit() and int(sesion_no) > 0 else None,
                inicio=_parse_dt(row.get("REUNION_INICIO")),
                fin=_parse_dt(row.get("REUNION_FIN")),
                camara=_na(row.get("SESION_CAMARA")),
                periodo_id=pid,
            )

    @staticmethod
    def _row_to_proyecto(row: dict) -> "HcdnProyecto | None":
        try:
            pid = (row.get("PROYECTO_ID") or "").strip()
            titulo = (row.get("TITULO") or "").strip()
            if not pid or not titulo:
                return None
            return HcdnProyecto(
                proyecto_id=pid,
                titulo=titulo,
                fecha_publicacion=_parse_fecha(row.get("PUBLICACION_FECHA")),
                camara_origen=_na(row.get("CAMARA_ORIGEN")),
                exp_diputados=_na(row.get("EXP_DIPUTADOS")),
                exp_senado=_na(row.get("EXP_SENADO")),
                tipo_proyecto=_na(row.get("TIPO")),
                autor=_na(row.get("AUTOR")),
            )
        except Exception:
            return None
