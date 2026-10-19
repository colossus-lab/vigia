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
