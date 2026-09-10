"""Tests del conector BORA: parsing del listado, clasificación y detección de DNU."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from vigia_connectors.bora import (
    LISTADO_TOPE,
    BoraAviso,
    listado_truncado,
    looks_like_dnu,
    parse_detalle_texto,
    parse_seccion_html,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _avisos():
    html = (FIXTURES / "bora_seccion_primera.html").read_text(encoding="utf-8")
    return parse_seccion_html(html, "primera", date(2026, 6, 10))


def test_parse_listado():
    avisos = _avisos()
    # 4 avisos reales: el link vacío se ignora y el duplicado ?anexos=1 se dedupea.
    assert [a.aviso_id for a in avisos] == ["342946", "342949", "342960", "342970"]
    decreto = avisos[0]
    assert decreto.organismo == "MINISTERIO DE SEGURIDAD NACIONAL"
    assert decreto.tipo_linea == "Decreto 436/2026"
    assert decreto.sumario.startswith("DECTO-2026-436")
    assert decreto.fecha == date(2026, 6, 10)
    assert decreto.url.endswith("/detalleAviso/primera/342946/20260610")


def test_clasificacion_y_numero():
    avisos = {a.aviso_id: a for a in _avisos()}
    assert avisos["342946"].tipo_slug() == "DECRETO"
    assert avisos["342946"].numero == "436/2026"
    # Decisión Administrativa -> DECRETO (misma convención que InfoLEG).
    assert avisos["342949"].tipo_slug() == "DECRETO"
    assert avisos["342949"].numero == "21/2026"
    assert avisos["342960"].tipo_slug() == "RESOLUCION"
    assert avisos["342970"].tipo_slug() == "LEY"
    assert avisos["342970"].numero == "27900"


def test_detalle_y_dnu():
    html = (FIXTURES / "bora_detalle_dnu.html").read_text(encoding="utf-8")
    texto = parse_detalle_texto(html)
    assert texto is not None
    assert "ARTÍCULO 1°" in texto
    assert looks_like_dnu(texto)  # art. 99 inc. 3 + Comisión Bicameral


def test_dnu_negativo():
    # Designación común por art. 99 inc. 7: NO es DNU.
    assert not looks_like_dnu("VISTO el artículo 99, inciso 7 de la CONSTITUCIÓN NACIONAL. DECRETA: ...")
    assert not looks_like_dnu(None)


def test_tipo_slug_dnu_explicito():
    a = BoraAviso(
        aviso_id="1", seccion="primera", fecha=date(2026, 6, 10),
        organismo="PEN", tipo_linea="Decreto de Necesidad y Urgencia 70/2026", sumario=None,
    )
    assert a.tipo_slug() == "DNU"
    assert a.numero == "70/2026"


def _listado_de(n: int) -> str:
    """Listado sintético de n avisos, con el markup real del sitio."""
    filas = "".join(
        f'''<a href="/detalleAviso/primera/{347000 + i}/20260908">
             <p class="item">ORGANISMO {i}</p>
             <p class="item-detalle">Resolución {i}/2026</p>
             <p class="item-detalle">Sumario del aviso {i}.</p>
           </a>'''
        for i in range(n)
    )
    return f'<html><body><h5 class="seccion-rubro">RESOLUCIONES</h5>{filas}</body></html>'


def test_listado_truncado_detecta_el_tope():
    """El sitio corta en 100 y no pagina: una edición de 100 está incompleta.

    Regresión del 2026-09-08, cuando la 1ª sección listó 100 avisos y los IDs
    posteriores existían igual para esa fecha (~247 reales).
    """
    completo = parse_seccion_html(_listado_de(LISTADO_TOPE - 1), "primera", date(2026, 9, 8))
    assert len(completo) == LISTADO_TOPE - 1
    assert listado_truncado(completo) is False

    tope = parse_seccion_html(_listado_de(LISTADO_TOPE), "primera", date(2026, 9, 8))
    assert len(tope) == LISTADO_TOPE
    assert listado_truncado(tope) is True


def test_listado_truncado_no_marca_ediciones_chicas():
    """Los días normales del BORA (30-90 avisos) no pueden disparar el warn."""
    assert listado_truncado(_avisos()) is False
    assert listado_truncado([]) is False
