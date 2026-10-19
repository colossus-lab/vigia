"""CKAN de HCDN para la sección Congreso: legisladores y sesiones.

Fixtures = recortes reales de datos.hcdn.gob.ar bajados el 2026-10-19:
`hcdn_legisladores_composicion.csv` (Composición Actual), `hcdn_legisladores_mandatos.csv`
(histórico "Diputados") y `hcdn_sesiones.csv`.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from vigia_connectors.hcdn import (
    HcdnClient,
    elegir_recurso_csv,
    legisladores_vigentes,
)

FIXTURES = Path(__file__).parent / "fixtures"
HOY = date(2026, 10, 19)

# Recursos tal cual los devuelve package_show?id=legisladores (URLs acortadas).
_RECURSOS = [
    {"format": "CSV", "name": "Diputados", "url": "https://x/diputados2.1.csv"},
    {"format": "CSV", "name": "Composición Actual de la Cámara", "url": "https://x/diputados_actuales2.2.csv"},
    {"format": "JSON", "name": "Diputados", "url": "https://x/diputados2.1.json"},
]


def _legisladores():
    mandatos = list(HcdnClient.iter_mandatos_csv(FIXTURES / "hcdn_legisladores_mandatos.csv"))
    actuales = list(HcdnClient.iter_composicion_csv(FIXTURES / "hcdn_legisladores_composicion.csv"))
    return mandatos, actuales


def test_elegir_recurso_csv_por_nombre():
    # Sin nombre: el primer CSV (el comportamiento de siempre de resolve_csv_url).
    assert elegir_recurso_csv(_RECURSOS) == "https://x/diputados2.1.csv"
    # Prefijo, sin importar tildes ni mayúsculas.
    assert elegir_recurso_csv(_RECURSOS, "composicion actual") == "https://x/diputados_actuales2.2.csv"
    # Exacto: "Diputados" no debe caer en el JSON ni en otro CSV.
    assert elegir_recurso_csv(_RECURSOS, "Diputados") == "https://x/diputados2.1.csv"
    assert elegir_recurso_csv(_RECURSOS, "Senadores") is None


def test_iter_composicion_y_mandatos():
    mandatos, actuales = _legisladores()
    assert len(actuales) == 7
    assert actuales[0].apellido == "Agüero"
    assert actuales[0].jura == date(2025, 12, 3)
    assert actuales[0].mandato == "2025-2029"
    alvarez = [m for m in mandatos if m.diputado_id == "HCDN3178"]
    assert [m.bloque for m in alvarez] == ["PAIS FEDERAL", "INNOVACIÓN FEDERAL", "ARGENTINA FEDERAL"]
    assert alvarez[0].inicio == date(2023, 12, 10)


def test_mandato_vigente_respeta_cese():
    mandatos, _ = _legisladores()
    # Pitrola renunció el 26/08/2026 con mandato hasta 2027: ya no está vigente.
    pitrola = next(m for m in mandatos if m.diputado_id == "HCDN3242")
    assert pitrola.fin == date(2027, 12, 9)
    assert pitrola.vigente(date(2026, 8, 1))
    assert not pitrola.vigente(HOY)


def test_legisladores_vigentes_cruza_por_apellido_distrito_y_nombre():
    mandatos, actuales = _legisladores()
    legs, sin_id = legisladores_vigentes(mandatos, actuales, HOY)
    assert sin_id == []
    por_nombre = {l.nombre: l for l in legs}
    assert len(por_nombre) == 7
    # Dos García por Buenos Aires: desempata el nombre.
    assert por_nombre["García, Álvaro"].external_id == "HCDN3248"
    assert por_nombre["García, María Teresa"].external_id == "HCDN0885"
    assert por_nombre["García, Carlos"].external_id == "HCDN3106"
    # Néstor Kirchner (mandato 2009) no puede quedarse con el ID de Máximo.
    assert por_nombre["Kirchner, Máximo Carlos"].external_id == "HCDN1489"


def test_legisladores_vigentes_usa_el_distrito_del_mandato_en_curso():
    # Bregman fue diputada por Buenos Aires (2013) y hoy lo es por CABA: la
    # llave tiene que salir del mandato vigente, no del primero.
    mandatos, actuales = _legisladores()
    legs, _ = legisladores_vigentes(mandatos, actuales, HOY)
    bregman = next(l for l in legs if l.nombre.startswith("Bregman"))
    assert bregman.external_id == "HCDN1435"
    assert bregman.distrito == "CIUDAD DE BUENOS AIRES"
    assert bregman.mandato_desde == date(2025, 12, 10)
    assert bregman.mandato_hasta == date(2029, 12, 9)


def test_legisladores_vigentes_bloque_actual_e_historial():
    mandatos, actuales = _legisladores()
    legs, _ = legisladores_vigentes(mandatos, actuales, HOY)
    alvarez = next(l for l in legs if l.external_id == "HCDN3178")
    assert alvarez.nombre == "Álvarez, Claudio"
    assert alvarez.bloque == "ARGENTINA FEDERAL"
    assert [b["bloque"] for b in alvarez.raw["bloques"]] == [
        "PAIS FEDERAL", "INNOVACIÓN FEDERAL", "ARGENTINA FEDERAL",
    ]


def test_legisladores_vigentes_sin_candidato_va_a_sin_id():
    mandatos, actuales = _legisladores()
    sin_maximo = [m for m in mandatos if m.diputado_id != "HCDN1489"]
    legs, sin_id = legisladores_vigentes(sin_maximo, actuales, HOY)
    assert [a.apellido for a in sin_id] == ["Kirchner"]
    assert len(legs) == 6


def test_iter_sesiones_csv():
    rows = list(HcdnClient.iter_sesiones_csv(FIXTURES / "hcdn_sesiones.csv"))
    assert len(rows) == 10
    r7 = rows[0]
    assert (r7.periodo, r7.asamblea, r7.reunion, r7.sesion_no) == (144, False, 7, 6)
    assert r7.inicio == datetime(2026, 9, 7, 12, 6)
    minoria = next(r for r in rows if r.reunion_tipo == "Minoría")
    assert minoria.sesion_no is None  # SESION_NO = 0
    asamblea = next(r for r in rows if r.asamblea)
    assert (asamblea.periodo_id, asamblea.reunion, asamblea.camara) == ("HCDN144A01", 1, "ASAMBLEA")
