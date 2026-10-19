"""Tests del conector de actividad del Senado (offline, fixtures reales bajados el 2026-10-19).

- `senado_actas_listado.html`: `/votaciones/actas` de 2026 recortado a 10 filas.
- `senado_acta_2628.html`: Modernización Laboral, Título V (PE-159/25-PL), voto nominal.
- `senado_acta_2847.html`: Carta Orgánica del BCRA, solo con O.D. (sin expediente).
- `senado_acta_2008.html`: acta 1624 (2008), filas SIN link al perfil del senador.
- `senado_acta_sin_votos.html`: acta 2750 (2009), real pero sin voto nominal.
- `senado_agenda.html`, `senado_sesiones_tac.html` (recortado a 31 de 1818 filas),
  `senado_senadores.json` y `senado_senadores_historico.json` (recortado a 131 períodos).
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from vigia_connectors.senado_actividad import (
    ART,
    VOTOS,
    IndiceSenadores,
    cargar_json_tolerante,
    id_sintetico,
    inferir_fecha,
    mapear_voto,
    parse_acta_detalle,
    parse_actas_listado,
    parse_agenda,
    parse_senadores_historico_json,
    parse_senadores_json,
    parse_sesiones_tac,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _leer(nombre: str) -> str:
    return (FIXTURES / nombre).read_text(encoding="utf-8")


# --- listado de actas --------------------------------------------------------

def _listado():
    return parse_actas_listado(_leer("senado_actas_listado.html"))


def test_listado_filas_y_campos():
    actas = _listado()
    assert len(actas) == 10
    a = next(x for x in actas if x.acta_id == "2623")
    assert a.fecha == date(2026, 2, 11)
    assert a.numero_acta == "1"
    assert a.titulo == "Modernización Laboral."
    assert a.etapa == "general"
    assert a.resultado == "afirmativo"
    assert a.mayoria == "SIMPLE"
    assert a.url == "https://www.senado.gob.ar/votaciones/detalleActa/2623"
    assert a.url_pdf == "https://www.senado.gob.ar/votaciones/verActaVotacion/2623"
    assert a.video_url == "https://www.youtube.com/watch?v=FrQ7k4GPUz8"


def test_listado_expedientes_canonicos_y_od():
    """Los expedientes del div oculto salen canónicos; la O.D. como `699/2025`."""
    a = next(x for x in _listado() if x.acta_id == "2628")
    assert a.expedientes == ["0159-PE-2025"]
    assert a.ordenes_del_dia == ["699/2025"]
    # El título no arrastra el "Ver Expedientes" ni el contenido oculto.
    assert a.titulo == "Modernización Laboral. Título V."


def test_listado_acta_solo_con_od():
    a = next(x for x in _listado() if x.acta_id == "2847")
    assert a.expedientes == []
    assert a.ordenes_del_dia == ["367/2026"]
    assert a.etapa == "particular"


def test_listado_etapa_general_y_particular():
    a = next(x for x in _listado() if x.acta_id == "2846")
    assert a.etapa == "general y particular"  # "EN GENERAL Y EN PARTICULAR"


def test_listado_sin_tabla_devuelve_vacio():
    assert parse_actas_listado("<html><body>mantenimiento</body></html>") == []


# --- detalle de acta ---------------------------------------------------------

def test_detalle_voto_nominal_2628():
    d = parse_acta_detalle(_leer("senado_acta_2628.html"), 2628)
    assert d is not None
    assert d.acta_id == "2628"
    assert d.numero_acta == "6"
    assert d.titulo == "Modernización Laboral. Título V."
    # Fecha de la sesión + hora de la votación (de madrugada), en hora argentina.
    assert d.fecha == datetime(2026, 2, 11, 2, 29, tzinfo=ART)
    assert d.resultado == "afirmativo"
    assert d.etapa == "particular"
    assert d.mayoria == "SIMPLE"
    assert (d.afirmativos, d.negativos, d.abstenciones, d.ausentes) == (42, 30, 0, 0)
    assert d.expedientes == ["0159-PE-2025"]
    assert d.ordenes_del_dia == ["699/2025"]

    assert len(d.votos) == 72
    v = d.votos[0]
    assert v.senador_id == "540"
    assert v.nombre == "MENDOZA, SANDRA MARIELA"
    assert v.bloque == "CONVICCIÓN FEDERAL"
    assert v.distrito == "TUCUMÁN"
    assert v.voto == "negativo"
    # Los totales cuadran con las filas.
    assert sum(x.voto == "afirmativo" for x in d.votos) == 42
    assert sum(x.voto == "negativo" for x in d.votos) == 30
    assert all(x.senador_id for x in d.votos)
    assert {x.voto for x in d.votos} <= set(VOTOS)


def test_detalle_solo_od_2847():
    d = parse_acta_detalle(_leer("senado_acta_2847.html"), "2847")
    assert d.expedientes == []
    assert d.ordenes_del_dia == ["367/2026"]
    assert d.titulo == "Modificación de la Carta Orgánica del Banco Central. Artículo 20."
    assert d.fecha == datetime(2026, 9, 24, 17, 44, tzinfo=ART)
    assert (d.afirmativos, d.negativos, d.abstenciones, d.ausentes) == (46, 22, 0, 4)
    assert sum(x.voto == "ausente" for x in d.votos) == 4


def test_detalle_2008_sin_links_de_senador():
    """El link `/senadores/senador/{ID}` solo aparece para quien HOY está en funciones.

    En esta acta de 2008 lo tiene una sola fila (Mayans, senador desde entonces);
    las otras 71 hay que resolverlas contra el histórico.
    """
    d = parse_acta_detalle(_leer("senado_acta_2008.html"), "1624")
    assert len(d.votos) == 72
    con_link = [v for v in d.votos if v.senador_id]
    assert [(v.senador_id, v.nombre) for v in con_link] == [("294", "MAYANS, JOSÉ MIGUEL ÁNGEL")]
    assert d.votos[0].nombre == "ESTENSSORO, MARÍA EUGENIA"
    assert d.votos[0].senador_id is None
    assert d.ordenes_del_dia == ["66/2008"]


def test_detalle_acta_real_sin_voto_nominal():
    d = parse_acta_detalle(_leer("senado_acta_sin_votos.html"), "2750")
    assert d is not None
    assert d.votos == []
    assert d.fecha.date() == date(2009, 3, 26)
    assert d.expedientes == ["0013-CD-2009"]
    assert d.mayoria == "ABSOLUTA"


def test_detalle_inexistente_devuelve_none():
    # Un ID que no existe devuelve 200 con la plantilla sin "Acta Nro".
    assert parse_acta_detalle("<html><body><h1>Votaciones</h1></body></html>", "99999") is None


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("AFIRMATIVO", "afirmativo"),
        ("NEGATIVO", "negativo"),
        ("ABSTENCIÓN", "abstencion"),
        ("ABSTENCION", "abstencion"),
        ("AUSENTE", "ausente"),
        ("PRESIDENTE", "presidente"),
        ("", "otro"),
        ("SE RETIRA", "otro"),
    ],
)
def test_mapear_voto(texto, esperado):
    assert mapear_voto(texto) == esperado


# --- senadores ---------------------------------------------------------------

def test_senadores_json():
    ss = parse_senadores_json(_leer("senado_senadores.json"))
    assert len(ss) == 72
    s = next(x for x in ss if x.external_id == "546")
    assert s.nombre == "ABAD, MAXIMILIANO"
    assert s.distrito == "BUENOS AIRES"
    assert s.bloque == "UCR - UNIÓN CÍVICA RADICAL"
    assert s.mandato_desde == date(2023, 12, 10)
    assert s.mandato_hasta == date(2029, 12, 9)


def test_json_tolerante_comas_colgantes():
    texto = '{"table": {"rows": [{"ID": "1", "APELLIDO": "X", "NOMBRE": "Y",},]},}'
    assert cargar_json_tolerante(texto) == {"table": {"rows": [{"ID": "1", "APELLIDO": "X", "NOMBRE": "Y"}]}}
    ss = parse_senadores_json(texto)
    assert [s.nombre for s in ss] == ["X, Y"]


def test_json_tolerante_no_toca_json_valido():
    assert cargar_json_tolerante('﻿{"a": ",}"}') == {"a": ",}"}


def test_indice_resuelve_todas_las_filas_del_acta_2008():
    """Con el histórico, cada fila sin link encuentra su ID por nombre + provincia."""
    hist = parse_senadores_historico_json(_leer("senado_senadores_historico.json"))
    indice = IndiceSenadores([*hist, *parse_senadores_json(_leer("senado_senadores.json"))])
    d = parse_acta_detalle(_leer("senado_acta_2008.html"), "1624")
    ids = [indice.resolver(v.nombre, v.distrito, d.fecha.date()) for v in d.votos]
    assert all(ids)
    assert len(set(ids)) == 72


def test_indice_homonimos_desempata_por_fecha():
    """Dos 'MARTÍNEZ, JULIO CÉSAR' de La Rioja: 1973-76 (3304) y 2017-23 (482)."""
    hist = parse_senadores_historico_json(_leer("senado_senadores_historico.json"))
    indice = IndiceSenadores(hist)
    assert indice.resolver("MARTÍNEZ, JULIO CÉSAR", "LA RIOJA", date(2019, 5, 2)) == "482"
    assert indice.resolver("MARTINEZ, JULIO CESAR", "LA RIOJA", date(1974, 8, 1)) == "3304"
    # Acentos y mayúsculas no importan.
    assert indice.resolver("rodríguez saá, adolfo", "San Luis", date(2010, 1, 1)) == "365"


def test_indice_no_resuelve_desconocidos():
    indice = IndiceSenadores(parse_senadores_json(_leer("senado_senadores.json")))
    assert indice.resolver("PÉREZ, NADIE", "MARTE", date(2026, 1, 1)) is None


def test_id_sintetico_estable_y_distinguible():
    a = id_sintetico("PÉREZ, JUAN", "SALTA")
    assert a == id_sintetico("perez, juan", "Salta")
    assert a != id_sintetico("PÉREZ, JUAN", "JUJUY")
    assert a.startswith("nom-") and len(a) <= 64


# --- agenda ------------------------------------------------------------------

def _agenda():
    return parse_agenda(_leer("senado_agenda.html"), hoy=date(2026, 10, 19))


def test_agenda_filas():
    rs = _agenda()
    assert len(rs) == 4
    r = rs[0]
    assert r.comision == "DE COPARTICIPACIÓN FEDERAL DE IMPUESTOS"
    assert r.fecha_hora == datetime(2026, 10, 20, 16, 0, tzinfo=ART)
    assert r.sala == "AZUL"
    assert r.tipo == "comisiones"
    assert r.temario and r.temario.startswith("REUNIÓN INFORMATIVA")
    assert [x.tipo for x in rs] == ["comisiones", "comisiones", "comisiones", "asesores"]


def test_agenda_expedientes_del_temario():
    rs = _agenda()
    rree = next(r for r in rs if "RELACIONES EXTERIORES" in r.comision)
    assert rree.fecha_hora == datetime(2026, 10, 21, 12, 0, tzinfo=ART)
    assert "0271-PE-2026" in rree.expedientes
    # "MENSAJE Nº 225/26" no es un expediente.
    assert not any(e.startswith("0225-") for e in rree.expedientes)


def test_agenda_expediente_partido_entre_tags():
    """El temario trae "S-285/2" y "5" en tags distintos: el link verExp lo rescata."""
    mineria = next(r for r in _agenda() if "MINERÍA" in r.comision)
    assert "0285-S-2025" in mineria.expedientes
    assert "S-285/25" in mineria.temario


def test_agenda_external_id_estable():
    a, b = _agenda(), _agenda()
    assert [r.external_id for r in a] == [r.external_id for r in b]
    assert len({r.external_id for r in a}) == len(a)


@pytest.mark.parametrize(
    ("dia", "d", "m", "hoy", "esperado"),
    [
        ("Martes", 20, 10, date(2026, 10, 19), date(2026, 10, 20)),
        # Corriendo en diciembre, una reunión de enero es del año siguiente.
        ("Martes", 5, 1, date(2026, 12, 28), date(2027, 1, 5)),
        # Y corriendo en enero, una de fines de diciembre es del año anterior.
        ("Miércoles", 30, 12, date(2027, 1, 2), date(2026, 12, 30)),
        # Sin acento también.
        ("Miercoles", 21, 10, date(2026, 10, 19), date(2026, 10, 21)),
    ],
)
def test_inferir_fecha(dia, d, m, hoy, esperado):
    assert inferir_fecha(dia, d, m, hoy) == esperado


def test_agenda_vacia():
    assert parse_agenda("<html><body><div class='sgr-group-title'>REUNIONES</div></body></html>",
                        date(2026, 10, 19)) == []


# --- sesiones ----------------------------------------------------------------

def test_sesiones_tac():
    ss = parse_sesiones_tac(_leer("senado_sesiones_tac.html"))
    assert len(ss) == 31
    s = ss[0]
    assert s.fecha == date(2026, 9, 24)
    assert s.tipo == "ORDINARIA"
    assert (s.numero_sesion, s.reunion) == (8, 11)
    assert s.external_id == "2026-09-24/11"
    assert s.url_taquigrafica.endswith("/parlamentario/sesiones/24-09-2026/11/downloadTac")
    assert s.url_diario.endswith("/parlamentario/sesiones/2768/descargarDiario")
    # Las de 1983 no tienen versión taquigráfica, solo diario.
    viejas = [x for x in ss if x.fecha.year == 1983]
    assert viejas and all(x.url_taquigrafica is None for x in viejas)
    assert len({x.external_id for x in ss}) == len(ss)
