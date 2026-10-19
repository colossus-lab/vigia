"""Shape-tests de los mappers de Diputados (sección Congreso) + helpers puros.

Cada `_to_row()` tiene que producir exactamente las columnas que se escriben:
las del modelo menos `id`, los timestamps y `search_vector` (GENERATED: si va
en el INSERT, Postgres lo rechaza). Una key de más rompe el INSERT; una de
menos deja la columna sin refrescar en el upsert.
"""
from __future__ import annotations

from datetime import date, datetime

from vigia_connectors.hcdn import HcdnLegislador
from vigia_connectors.hcdn_actividad import ART, HcdnAsunto, HcdnReunion, HcdnSesion
from vigia_shared.models import AsuntoTratado, CongresoSesion, Legislador, ReunionComision
from vigia_shared.sources import SOURCES
from vigia_workers.congreso_hcdn import (
    _asunto_to_row,
    _legislador_to_row,
    _reunion_to_row,
    _sesion_to_row,
    agenda_vacia_sospechosa,
    bajas_agenda,
    sesiones_a_recorrer,
)

_NO_SE_ESCRIBEN = {"id", "ingested_at", "updated_at", "search_vector"}


def _cols(model) -> set[str]:
    return {c.name for c in model.__table__.columns} - _NO_SE_ESCRIBEN


def _sesion(periodo=144, reunion=6, fecha=date(2026, 8, 26), asamblea=False, numero=5) -> HcdnSesion:
    return HcdnSesion(
        periodo=periodo, reunion=reunion, asamblea=asamblea, numero_sesion=numero,
        fecha=fecha, tipo="Sesión Ordinaria Especial", url=None, raw={},
    )


def test_legislador_to_row_shape():
    row = _legislador_to_row(HcdnLegislador(
        external_id="HCDN3178", nombre="Álvarez, Claudio", bloque="ARGENTINA FEDERAL",
        distrito="SAN LUIS", mandato_desde=date(2023, 12, 10), mandato_hasta=date(2027, 12, 9),
        raw={"bloques": []},
    ))
    assert set(row) == _cols(Legislador)
    assert row["camara"] == "D"
    assert row["activo"] is True  # reactiva a quien vuelve a la nómina


def test_sesion_to_row_shape():
    row = _sesion_to_row(_sesion())
    assert set(row) == _cols(CongresoSesion)
    assert row["external_id"] == "144-6"
    assert _sesion_to_row(_sesion(reunion=1, asamblea=True))["external_id"] == "144-A1"


def test_asunto_to_row_shape():
    a = HcdnAsunto(
        orden=3, clave="0007-PE-2026", expedientes=["0007-PE-2026", "0171-D-2025"],
        orden_del_dia="211", tipo="LEY", sumario="Carta Orgánica del BCRA. Modificación.",
        resultado="APROBADO SIN MODIFICACIONES", detalle=["Se comunicó al H. Senado"], links=[],
    )
    row = _asunto_to_row(a, sesion_id=42)
    assert set(row) == _cols(AsuntoTratado)
    assert row["sesion_id"] == 42
    assert row["raw"]["orden"] == 3


def test_reunion_to_row_shape():
    r = HcdnReunion(
        external_id="1365", fecha_hora=datetime(2026, 10, 20, 10, 0, tzinfo=ART),
        comision="PRESUPUESTO Y HACIENDA", comisiones=["PRESUPUESTO Y HACIENDA"],
        slugs=["cpyhacienda"], sala='Anexo "C" - 2° piso', tipo="Informativa",
        temario="INVITADOS.", expedientes=[], url_citacion=None, reun_id="1365",
    )
    row = _reunion_to_row(r)
    assert set(row) == _cols(ReunionComision)
    assert "search_vector" not in row


def test_sesiones_a_recorrer():
    hoy = date(2026, 10, 19)
    ses = [
        _sesion(reunion=9, fecha=date(2026, 10, 21), numero=7),  # futura
        _sesion(reunion=8, fecha=date(2026, 10, 15), numero=None),  # reciente
        _sesion(reunion=6, fecha=date(2026, 8, 26)),  # vieja
        _sesion(periodo=143, reunion=22, fecha=date(2026, 2, 19), numero=3),
        _sesion(reunion=1, fecha=date(2026, 10, 1), asamblea=True),  # asamblea: sin BAT
    ]
    assert [s.external_id for s in sesiones_a_recorrer(ses, hoy)] == ["144-8"]
    backfill = sesiones_a_recorrer(ses, hoy, periodos=[144, 143])
    assert [s.external_id for s in backfill] == ["144-8", "144-6", "143-22"]


def test_agenda_vacia_sospechosa():
    assert agenda_vacia_sospechosa(0, date(2026, 10, 20))  # martes de octubre
    assert not agenda_vacia_sospechosa(3, date(2026, 10, 20))
    assert not agenda_vacia_sospechosa(0, date(2026, 10, 23))  # viernes
    assert not agenda_vacia_sospechosa(0, date(2026, 1, 13))  # receso


def test_fuentes_registradas_sin_slo():
    for code in ("hcdn_sesiones", "hcdn_asuntos", "hcdn_agenda", "hcdn_legisladores"):
        assert SOURCES[code]["code"] == code
        assert SOURCES[code]["freshness_slo_days"] is None


def test_bajas_agenda_sin_dias_no_borra_nada():
    # Página rota o vacía: lo avisa el warn, no se lee como "se suspendió todo".
    ahora = datetime(2026, 10, 20, 9, 0, tzinfo=ART)
    assert bajas_agenda([], ["1365"], ahora) is None
    assert bajas_agenda([], [], ahora) is None


def test_bajas_agenda_parametros():
    ahora = datetime(2026, 10, 20, 9, 0, tzinfo=ART)
    dias = [date(2026, 10, 21), date(2026, 10, 20), date(2026, 10, 20)]
    p = bajas_agenda(dias, ["1365", "1363", "1365"], ahora)
    assert p == {
        "c": "D",
        "ahora": ahora,  # el pasado no se toca: ya no figura en la agenda
        "dias": [date(2026, 10, 20), date(2026, 10, 21)],
        "ids": ["1363", "1365"],
    }
    # Días con solo sesión de recinto: no quedó ninguna reunión de comisión,
    # así que las futuras de esos días se dan de baja.
    assert bajas_agenda([date(2026, 10, 21)], [], ahora)["ids"] == []


def test_bajas_agenda_cubre_los_dias_sin_encabezado():
    # El jueves tenía una sola reunión y se suspendió: el jueves desaparece de la
    # página. Igual está cubierto, porque la agenda llega hasta el viernes.
    ahora = datetime(2026, 10, 20, 9, 0, tzinfo=ART)  # martes
    p = bajas_agenda([date(2026, 10, 20), date(2026, 10, 23)], ["1"], ahora)
    assert p["dias"] == [date(2026, 10, d) for d in (20, 21, 22, 23)]


def test_bajas_agenda_no_toca_el_pasado_ni_lo_que_la_pagina_no_muestra():
    ahora = datetime(2026, 10, 20, 9, 0, tzinfo=ART)
    # La página muestra la semana entera, incluidos días que ya pasaron: el
    # rango arranca hoy y termina en el último día mostrado (no después).
    p = bajas_agenda([date(2026, 10, 19), date(2026, 10, 21)], [], ahora)
    assert p["dias"] == [date(2026, 10, 20), date(2026, 10, 21)]
    # Una agenda que solo trae días pasados no cubre nada futuro.
    assert bajas_agenda([date(2026, 10, 19)], [], ahora) is None
