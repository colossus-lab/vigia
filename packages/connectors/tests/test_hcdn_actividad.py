"""Scrape de www.hcdn.gob.ar: agenda de comisiones, listado de sesiones y BAT.

Todos los fixtures son HTML real bajado el 2026-10-19:
- `hcdn_agenda.html`: /comisiones/agenda/ completo (semana del 20/10/2026).
- `hcdn_sesiones_listado.html`: recorte de /sesiones/ (períodos 144, 143 y 142).
- `hcdn_bat.html`: BAT periodo=144&reunion=6&sesion=5 (formato actual, 23 asuntos).
- `hcdn_bat_2012.html`: BAT periodo=130&reunion=5&sesion=4 (formato viejo, sin <p>).
- `hcdn_bat_partido.html`: BAT periodo=143&reunion=22&sesion=3 (sanción partida en dos <p>).
- `hcdn_bat_vacio.html`: BAT de una sesión que todavía no se hizo (wrapper vacío).
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from vigia_connectors.hcdn import HcdnClient
from vigia_connectors.hcdn_actividad import (
    ART,
    combinar_sesiones,
    en_receso,
    parse_agenda,
    parse_bat,
    parse_sesiones_listado,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _html(nombre: str) -> str:
    return (FIXTURES / nombre).read_text(encoding="utf-8")


# ─────────────────────────────────── Agenda ───────────────────────────────────


def test_parse_agenda_reuniones():
    ag = parse_agenda(_html("hcdn_agenda.html"))
    assert ag.dias == [date(2026, 10, 20), date(2026, 10, 21)]
    assert [r.external_id for r in ag.reuniones] == ["1365", "1363", "1362", "1364"]

    r = ag.reuniones[0]
    assert r.fecha_hora == datetime(2026, 10, 20, 10, 0, tzinfo=ART)
    assert r.comision == "PRESUPUESTO Y HACIENDA"
    assert r.slugs == ["cpyhacienda"]
    assert r.sala == 'Anexo "C" - 2° piso'
    assert r.tipo == "Informativa"
    assert r.temario.startswith("INVITADOS. Fueron invitados el Secretario de Educación")
    assert "ver citación" not in r.temario
    assert r.url_citacion == (
        "https://parlamentaria.hcdn.gob.ar/comisiones/reuniones/1365/archivo/8WG73728B2T7JFVW.pdf"
    )


def test_parse_agenda_reunion_conjunta():
    ag = parse_agenda(_html("hcdn_agenda.html"))
    conj = next(r for r in ag.reuniones if r.external_id == "1364")
    assert conj.comisiones == ["DEFENSA NACIONAL", "LEGISLACION PENAL", "RELACIONES EXTERIORES Y CULTO"]
    assert conj.comision == "DEFENSA NACIONAL, LEGISLACION PENAL, RELACIONES EXTERIORES Y CULTO"
    assert conj.tipo == "Conjunta"
    assert conj.sala == 'Anexo "C" - 2° piso'
    informativa = next(r for r in ag.reuniones if r.external_id == "1363")
    assert informativa.tipo == "Informativa · Conjunta"
    assert informativa.sala == 'Sala 1 - Anexo "A"'


def test_parse_agenda_no_carga_el_recinto_como_comision():
    ag = parse_agenda(_html("hcdn_agenda.html"))
    assert all("SESI" not in r.comision for r in ag.reuniones)
    assert len(ag.recinto) == 1
    sesion = ag.recinto[0]
    assert sesion["reun_id"] == "3587"  # == id del listado de sesiones
    assert sesion["titulo"] == "SESIÓN ESPECIAL"
    assert sesion["expedientes"] == ["0032-S-2026"]


def test_parse_agenda_sin_reunid_usa_hash_estable():
    html = """
    <table id="agendaComisiones">
      <thead><tr><th colspan=2> lunes 19 de octubre del 2026</th></tr></thead>
      <tr><td><strong>11:00</strong><br/>Sala 2 - Anexo "A" - Ordinaria<br>
          <span class='leyenda'> </span><br></td>
          <td><a href="/comisiones/permanentes/cagricultura"><strong>AGRICULTURA Y GANADERIA</strong></a>
          <h5></h5><strong></strong><br>Consideración del expediente 1234-D-2026.<br/></td></tr>
    </table>
    """
    a = parse_agenda(html).reuniones
    b = parse_agenda(html).reuniones
    assert len(a) == 1
    assert a[0].external_id == b[0].external_id
    assert a[0].external_id.startswith("h")
    assert a[0].reun_id is None
    assert a[0].expedientes == ["1234-D-2026"]
    assert a[0].tipo == "Ordinaria"


def test_parse_agenda_sin_tabla():
    ag = parse_agenda("<html><body><p>Sin reuniones</p></body></html>")
    assert ag.reuniones == [] and ag.dias == []


def test_en_receso():
    assert en_receso(date(2026, 1, 20))
    assert en_receso(date(2026, 7, 20))
    assert en_receso(date(2026, 12, 28))
    assert not en_receso(date(2026, 10, 19))
    assert not en_receso(date(2026, 7, 7))


# ─────────────────────────────── Listado de sesiones ───────────────────────────────


def test_parse_sesiones_listado():
    ses, descartadas = parse_sesiones_listado(_html("hcdn_sesiones_listado.html"))
    # 4 links con reunion=null (citadas no efectuadas, presentación del presupuesto).
    assert descartadas == 4
    assert len(ses) == 17
    s = ses[0]
    assert (s.site_id, s.periodo, s.reunion, s.numero_sesion) == ("3587", 144, 9, 7)
    assert s.fecha == date(2026, 10, 21)
    assert s.tipo == "Sesión Ordinaria Especial"
    assert s.url == "https://www.hcdn.gob.ar/sesiones/sesion.html?id=3587&numVid=0&reunion=9&periodo=144"
    minoria = next(x for x in ses if x.site_id == "3586")
    assert (minoria.tipo, minoria.numero_sesion) == ("Expresiones en Minoría", None)
    prep = next(x for x in ses if x.site_id == "3571")
    assert (prep.tipo, prep.numero_sesion) == ("Sesión Preparatoria", None)
    asamblea = next(x for x in ses if x.asamblea)
    assert (asamblea.periodo, asamblea.reunion, asamblea.tipo) == (144, 1, "Asamblea Legislativa")


def test_combinar_sesiones_mide_el_desfase_del_csv():
    sitio, _ = parse_sesiones_listado(_html("hcdn_sesiones_listado.html"))
    csv_rows = list(HcdnClient.iter_sesiones_csv(FIXTURES / "hcdn_sesiones.csv"))
    ses, desfase = combinar_sesiones(csv_rows, sitio)
    # El CSV viene 2 días antes que el sitio (y que el "se levanta la sesión" del BAT).
    assert desfase == 2
    por_id = {s.external_id: s for s in ses}
    s6 = por_id["144-6"]
    assert s6.fecha == date(2026, 8, 26)
    assert s6.raw["inicio"] == "2026-08-26T12:17:00"
    assert s6.raw["fin"] == "2026-08-27T03:47:00"  # BAT: "03:47 horas, del día 27 de agosto"
    assert s6.bat_url == "https://www.hcdn.gob.ar/secparl/dsecretaria/bat/bat.jsp?periodo=144&reunion=6&sesion=5"
    # La reunión 1 y la Asamblea del período 144 numeran las dos "1".
    assert por_id["144-1"].asamblea is False
    asamblea = por_id["144-A1"]
    assert asamblea.bat_url is None
    assert asamblea.tipo == "Asamblea Legislativa - Apertura Ordinarias"
    # Sesión que todavía no está en el CSV: solo sitio, sin horas.
    s9 = por_id["144-9"]
    assert s9.fecha == date(2026, 10, 21) and "inicio" not in s9.raw
    # Minoría: sin número de sesión, el BAT va con sesion=0.
    assert por_id["144-8"].bat_url.endswith("periodo=144&reunion=8&sesion=0")


def test_combinar_sesiones_sin_ckan():
    sitio, _ = parse_sesiones_listado(_html("hcdn_sesiones_listado.html"))
    ses, desfase = combinar_sesiones([], sitio)
    assert desfase == 0
    assert len(ses) == 17
    assert len({s.external_id for s in ses}) == 17


# ─────────────────────────── Boletín de Asuntos Tratados ───────────────────────────


def test_parse_bat_formato_actual():
    asuntos = parse_bat(_html("hcdn_bat.html"))
    assert len(asuntos) == 23  # la fila final "se levanta la sesión" no cuenta
    bcra = asuntos[2]
    assert bcra.clave == "0007-PE-2026"
    assert bcra.expedientes == ["0007-PE-2026", "0171-D-2025", "2888-D-2025"]
    assert bcra.orden_del_dia == "211"
    assert bcra.tipo == "LEY"
    assert bcra.resultado == "APROBADO SIN MODIFICACIONES"
    assert bcra.detalle == ["Se comunicó al H. Senado"]
    assert bcra.sumario.startswith("Carta Orgánica del Banco Central")
    assert bcra.links[0]["url"].endswith("/BAT2026/PDF/OD-211.pdf")

    sancionado = next(a for a in asuntos if a.clave == "0026-S-2026")
    assert sancionado.resultado == "SANCIONADO DEFINITIVAMENTE"
    assert sancionado.detalle == ["LEY N° 27.819"]


def test_parse_bat_clave_sin_expediente_ni_od():
    asuntos = parse_bat(_html("hcdn_bat.html"))
    jura = asuntos[1]
    assert jura.clave == "#2"
    assert (jura.expedientes, jura.orden_del_dia, jura.tipo, jura.resultado) == ([], None, None, None)
    assert jura.sumario.startswith("Jura e incorporación")
    homenaje = asuntos[3]
    assert (homenaje.clave, homenaje.resultado) == ("#4", "RENDIDO")
    assert len({a.clave for a in asuntos}) == len(asuntos)


def test_parse_bat_expediente_partido_en_tags_del_tema():
    # "(Se da por cumplido expediente 4153<em>-D-2026</em>)": si el texto se
    # separara por tag, el expediente quedaría roto y no cruzaría con nada.
    asuntos = parse_bat(_html("hcdn_bat.html"))
    trelew = asuntos[4]
    assert "Trelew" in trelew.sumario
    assert trelew.expedientes == ["4153-D-2026"]
    assert trelew.clave == "4153-D-2026"


def test_parse_bat_sancion_partida_en_dos_parrafos():
    asuntos = parse_bat(_html("hcdn_bat_partido.html"))
    assert len(asuntos) == 5
    laboral = asuntos[-1]
    # "65-S-25" en el boletín → canónico.
    assert laboral.clave == "0065-S-2025"
    assert laboral.orden_del_dia == "6"
    assert laboral.resultado == "APROBADO SIN MODIFICACIONES"
    assert laboral.detalle == ["Vuelve al H. Senado"]
    assert [l["texto"] for l in laboral.links] == ["VER TEXTO", "ANEXO"]


def test_parse_bat_formato_2012():
    asuntos = parse_bat(_html("hcdn_bat_2012.html"))
    assert len(asuntos) == 10
    assert asuntos[0].clave == "2267-D-2012"
    assert asuntos[4].orden_del_dia is None  # "S/T" (sin trámite)
    assert asuntos[4].tipo == "RESOLUCIÓN"
    assert asuntos[4].resultado == "APROBADO SIN MODIFICACIONES"
    codigo = asuntos[-1]
    assert codigo.orden_del_dia == "202"
    assert len(codigo.expedientes) == 15
    assert codigo.resultado == "APROBADO CON MODIFICACIONES"


def test_parse_bat_vacio():
    assert parse_bat(_html("hcdn_bat_vacio.html")) == []
