"""Tests del conector Senado: parsing del listado y del detalle (offline, fixtures)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from vigia_connectors.senado import parse_detalle, parse_listado

FIXTURES = Path(__file__).parent / "fixtures"


def _listado():
    html = (FIXTURES / "senado_listado.html").read_text(encoding="utf-8")
    return parse_listado(html)


def test_parse_listado_filas():
    ps = _listado()
    assert len(ps) >= 5
    p = ps[0]
    assert p.external_id == "1040/26-S-PL"
    assert p.tipo_codigo == "PL"
    assert p.origen == "S"
    assert p.tipo_slug() == "PROYECTO"
    assert "PROYECTO DE LEY" in p.extracto.upper()
    assert p.url.endswith("/verExp/1040.26/S/PL")


def test_external_id_unicos_y_formato():
    ps = _listado()
    ids = [p.external_id for p in ps]
    assert len(ids) == len(set(ids))  # sin duplicados
    for eid in ids:
        assert "/" in eid and eid.count("-") == 2  # nnnn/aa-ORIGEN-TIPO


def test_parse_detalle_fecha_y_autores():
    html = (FIXTURES / "senado_detalle.html").read_text(encoding="utf-8")
    det = parse_detalle(html)
    assert det["fecha"] == date(2026, 6, 12)  # Mesa de Entradas
    assert det["autores"] and "Valenzuela" in det["autores"][0]


def test_parse_listado_vacio():
    assert parse_listado("<html><body>nada</body></html>") == []


def test_origenes_ingesta_no_duplican_hcdn_pero_cubren_el_ejecutivo():
    from vigia_connectors.senado import ORIGENES_INGESTA

    # CD ya entra por hcdn_proyectos; sin PE/JGM las votaciones del Senado sobre
    # proyectos del Ejecutivo no tendrían proyecto contra el cual cruzarse.
    assert "CD" not in ORIGENES_INGESTA
    assert {"S", "PE", "JGM"} <= set(ORIGENES_INGESTA)


def test_external_id_del_senado_normaliza_al_mismo_expediente_que_la_votacion():
    from vigia_connectors.senado import SenadoProyecto
    from vigia_shared.expedientes import normalizar_expediente

    p = SenadoProyecto(numero="159", anio="25", tipo_codigo="PL", origen="PE", extracto="x")
    # El acta de votación lo cita como "PE-159/25-PL".
    assert normalizar_expediente(p.external_id) == normalizar_expediente("PE-159/25-PL")


def test_form_busqueda_filtra_por_origen_y_anio():
    from vigia_connectors.senado import form_busqueda

    f = form_busqueda("PL", origen="PE", anio=2025, token="tok")
    assert f["busqueda_proyectos[expedienteTipo]"] == "PL"
    assert f["busqueda_proyectos[expedienteLugar]"] == "PE"
    assert f["busqueda_proyectos[expedienteNumeroPos]"] == "2025"
    assert f["busqueda_proyectos[_token]"] == "tok"
    # Sin origen ni año, los campos van vacíos (= sin filtro), no ausentes.
    g = form_busqueda("PD")
    assert g["busqueda_proyectos[expedienteLugar]"] == ""
    assert g["busqueda_proyectos[expedienteNumeroPos]"] == ""


def test_parse_listado_filtrado_por_poder_ejecutivo():
    # Real (2026-10-19): PE + PL + 2025. Modernización Laboral es el 159/25.
    html = (FIXTURES / "senado_listado_pe_2025.html").read_text(encoding="utf-8")
    ids = [p.external_id for p in parse_listado(html)]
    assert ids == ["161/25-PE-PL", "159/25-PE-PL"]


class _FakeSenado:
    """SenadoClient con `buscar` falso: páginas por (tipo, origen)."""

    def __init__(self, paginas):
        from vigia_connectors.senado import SenadoClient

        self._paginas = paginas
        self.llamadas: list[tuple] = []
        self._buscar = SenadoClient._buscar.__get__(self)
        self._buscar_paginas = SenadoClient._buscar_paginas.__get__(self)
        self.fetch_recientes = SenadoClient.fetch_recientes.__get__(self)
        self.fetch_anio = SenadoClient.fetch_anio.__get__(self)

    async def buscar(self, tipo, page=1, *, origen="", anio=None):
        self.llamadas.append((tipo, origen, anio, page))
        pags = self._paginas.get((tipo, origen), [])
        return pags[page - 1] if page <= len(pags) else []

    async def fetch_detalle(self, p):  # pragma: no cover - con_detalle=False
        raise AssertionError("no debería bajar detalles")


def _p(num, origen, tipo="PL", anio="26"):
    from vigia_connectors.senado import SenadoProyecto

    return SenadoProyecto(numero=str(num), anio=anio, tipo_codigo=tipo, origen=origen, extracto="x")


async def test_fetch_recientes_busca_origen_por_origen():
    # Mezclados, los S llenarían las 3 páginas y el PE no aparecería nunca: por
    # eso cada origen tiene su propia búsqueda (y sus propias páginas).
    fake = _FakeSenado({
        ("PL", "S"): [[_p(i, "S") for i in range(100, 90, -1)]] * 5,
        ("PL", "PE"): [[_p(159, "PE", anio="25")]],
    })
    out = await fake.fetch_recientes(tipos=("PL",), max_pages=3, origenes=("S", "PE"), con_detalle=False)
    assert {p.external_id for p in out} >= {"159/25-PE-PL", "100/26-S-PL"}
    # S se corta en max_pages; PE en la primera página vacía.
    assert [c for c in fake.llamadas if c[1] == "S"] == [("PL", "S", None, n) for n in (1, 2, 3)]
    assert [c for c in fake.llamadas if c[1] == "PE"] == [("PL", "PE", None, 1), ("PL", "PE", None, 2)]


async def test_fetch_anio_pagina_hasta_la_vacia_y_pasa_el_anio():
    fake = _FakeSenado({("PL", "PE"): [[_p(i, "PE", anio="12")] for i in range(5)]})
    out = await fake.fetch_anio(2012, tipos=("PL",), origenes=("PE",), con_detalle=False)
    assert len(out) == 5
    assert fake.llamadas[-1] == ("PL", "PE", 2012, 6)  # la 6ª vino vacía y cortó
