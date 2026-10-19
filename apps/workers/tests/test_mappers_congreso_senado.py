"""Shape-tests de los mappers de `congreso_senado` (patrón de `test_mappers.py`).

Cada `_to_row()` va directo a un `pg insert(...).values(dicts)`: una key que
no es columna rompe el INSERT, y mandar `search_vector` (GENERATED) lo hace
rechazar por Postgres. Por eso se chequea contra las columnas del modelo.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from vigia_connectors.senado_actividad import (
    ART,
    ActaListado,
    ReunionAgenda,
    Senador,
    SesionTac,
    VotoNominal,
    parse_acta_detalle,
    parse_actas_listado,
)
from vigia_shared.models import CongresoSesion, Legislador, ReunionComision, Votacion, Voto
from vigia_workers.congreso_senado import (
    _historico_a_senadores,
    _legislador_desde_voto,
    _resolver_ids,
    _reunion_to_row,
    _senador_to_row,
    _sesion_to_row,
    _votacion_to_row,
    _voto_to_row,
    agenda_vacia_sospechosa,
    en_receso,
    reuniones_a_dar_de_baja,
)

FIXTURES = Path(__file__).parents[3] / "packages" / "connectors" / "tests" / "fixtures"

# Columnas que el mapper nunca manda: las pone la base o otro paso.
_NUNCA = {"id", "search_vector", "ingested_at", "updated_at", "sesion_id"}


def _columnas(model) -> set[str]:
    return {c.name for c in model.__table__.columns}


def _requeridas(model) -> set[str]:
    return {
        c.name for c in model.__table__.columns
        if not c.nullable and c.server_default is None and not c.primary_key
    }


def _chequear(row: dict, model) -> None:
    keys = set(row)
    assert keys <= _columnas(model) - _NUNCA, keys - (_columnas(model) - _NUNCA)
    assert _requeridas(model) <= keys, _requeridas(model) - keys


def _acta_2628():
    return parse_acta_detalle(
        (FIXTURES / "senado_acta_2628.html").read_text(encoding="utf-8"), "2628"
    )


def _listado_2628():
    actas = parse_actas_listado(
        (FIXTURES / "senado_actas_listado.html").read_text(encoding="utf-8")
    )
    return next(a for a in actas if a.acta_id == "2628")


def test_votacion_to_row_shape_con_detalle():
    row = _votacion_to_row(_listado_2628(), _acta_2628())
    _chequear(row, Votacion)
    assert row["camara"] == "S"
    assert row["external_id"] == "2628"
    assert row["fecha"] == datetime(2026, 2, 11, 2, 29, tzinfo=ART)
    assert row["expedientes"] == ["0159-PE-2025"]
    assert row["ordenes_del_dia"] == ["699/2025"]
    assert (row["afirmativos"], row["negativos"]) == (42, 30)
    assert row["video_url"].startswith("https://www.youtube.com/")
    assert "votos" not in row["raw"]["detalle"]  # los votos van a su tabla


def test_votacion_to_row_solo_listado():
    """Detalle caído: entra desde el listado, con la fecha a las 00:00 ART."""
    row = _votacion_to_row(_listado_2628(), None)
    _chequear(row, Votacion)
    assert row["fecha"] == datetime(2026, 2, 11, tzinfo=ART)
    assert row["afirmativos"] is None
    assert row["titulo"] == "Modernización Laboral. Título V."


def test_votacion_to_row_misma_forma_con_y_sin_detalle():
    # Se insertan en lotes distintos, pero el set de columnas tiene que ser el mismo.
    assert set(_votacion_to_row(_listado_2628(), None)) == set(
        _votacion_to_row(_listado_2628(), _acta_2628())
    )


def test_voto_to_row_shape():
    v = _acta_2628().votos[0]
    row = _voto_to_row(10, 20, v)
    assert set(row) <= _columnas(Voto)
    assert row == {"votacion_id": 10, "legislador_id": 20, "voto": "negativo",
                   "bloque": "CONVICCIÓN FEDERAL", "distrito": "TUCUMÁN"}


def test_legislador_desde_voto_shape():
    v = VotoNominal(senador_id=None, nombre="ESTENSSORO, MARÍA EUGENIA",
                    bloque="ALIANZA COALICIÓN CÍVICA", distrito="CIUDAD AUTÓNOMA DE BUENOS AIRES",
                    voto="negativo", voto_texto="NEGATIVO")
    row = _legislador_desde_voto(v, "999")
    _chequear(row, Legislador)
    assert row["activo"] is False  # sin link al perfil = ya no está en funciones


def test_senador_to_row_shape():
    s = Senador(external_id="546", nombre="ABAD, MAXIMILIANO", distrito="BUENOS AIRES",
                bloque="UCR", partido="JxC", mandato_desde=date(2023, 12, 10),
                mandato_hasta=date(2029, 12, 9), raw={"ID": "546"})
    row = _senador_to_row(s, activo=True)
    _chequear(row, Legislador)
    assert row["bloque"] == "UCR"


def test_historico_a_senadores_colapsa_periodos():
    def p(desde, hasta, partido):
        return Senador(external_id="365", nombre="RODRÍGUEZ SAÁ, ADOLFO", distrito="SAN LUIS",
                       bloque=None, partido=partido, mandato_desde=desde, mandato_hasta=hasta,
                       raw={"p": partido})
    viejo = Senador(external_id="3519", nombre="RODRIGUEZ SAA, ADOLFO", distrito="SAN LUIS",
                    bloque=None, partido="DEMOCRATA", mandato_desde=date(1923, 3, 17),
                    mandato_hasta=date(1933, 6, 16), raw={})
    actual = p(date(2023, 12, 10), None, "X")
    actual.external_id = "999"
    out = _historico_a_senadores(
        [p(date(2017, 12, 10), date(2023, 12, 9), "FRENTE"), p(date(2005, 12, 10), date(2011, 12, 9), "ALIANZA"),
         viejo, actual],
        excluir={"999"},
    )
    assert [s.external_id for s in out] == ["365"]  # el de 1923 y el actual quedan afuera
    s = out[0]
    assert (s.mandato_desde, s.mandato_hasta) == (date(2005, 12, 10), date(2023, 12, 9))
    assert s.partido == "FRENTE"
    assert len(s.raw["periodos"]) == 2
    _chequear(_senador_to_row(s, activo=False), Legislador)


def test_resolver_ids_link_indice_y_sintetico():
    d = _acta_2628()
    d.votos[1].senador_id = None  # simula un ex senador sin link

    class Indice:
        def resolver(self, nombre, distrito, fecha):
            return "777" if nombre == d.votos[1].nombre else None

    ids, st = _resolver_ids([d], Indice())
    assert ids[("2628", 0)] == "540"
    assert ids[("2628", 1)] == "777"
    assert st == {"por_link": 71, "por_indice": 1, "sinteticos": 0}

    ids, st = _resolver_ids([d], None)
    assert ids[("2628", 1)].startswith("nom-")
    assert st["sinteticos"] == 1


def test_reunion_to_row_shape():
    r = ReunionAgenda(external_id="abc", fecha_hora=datetime(2026, 10, 20, 16, 0, tzinfo=ART),
                      comision="DE PRESUPUESTO", sala="AZUL", tipo="comisiones",
                      temario="S-1042/26", expedientes=["1042-S-2026"], raw={"dia": "Martes 20"})
    row = _reunion_to_row(r)
    _chequear(row, ReunionComision)
    assert row["camara"] == "S"


def test_sesion_to_row_shape():
    s = SesionTac(fecha=date(2026, 9, 24), tipo="ORDINARIA", numero_sesion=8, reunion=11,
                  url_taquigrafica="https://x/tac", url_diario="https://x/diario")
    row = _sesion_to_row(s)
    _chequear(row, CongresoSesion)
    assert row["external_id"] == "2026-09-24/11"
    assert row["url"] == "https://x/tac"
    assert row["raw"]["fecha"] == "2026-09-24"  # JSONB: nada de objetos date


def test_receso_y_agenda_vacia():
    assert en_receso(date(2027, 1, 15)) and en_receso(date(2027, 2, 27))
    assert en_receso(date(2026, 7, 20))
    assert not en_receso(date(2026, 7, 2)) and not en_receso(date(2026, 10, 19))
    assert agenda_vacia_sospechosa(date(2026, 10, 19))      # lunes
    assert not agenda_vacia_sospechosa(date(2026, 10, 23))  # viernes
    assert not agenda_vacia_sospechosa(date(2026, 10, 24))  # sábado
    assert not agenda_vacia_sospechosa(date(2027, 2, 2))    # receso


def test_listado_acta_tiene_url():
    a = ActaListado(acta_id="1", fecha=date(2026, 1, 1), numero_acta=None, titulo="t", etapa=None,
                    resultado=None, mayoria=None, expedientes=[], ordenes_del_dia=[],
                    url_pdf=None, video_url=None)
    assert _votacion_to_row(a, None)["url"].endswith("/votaciones/detalleActa/1")


def test_reuniones_a_dar_de_baja():
    ahora = datetime(2026, 10, 20, 12, 0, tzinfo=ART)

    def r(eid, d, h):
        return {"external_id": eid, "fecha_hora": datetime(2026, 10, d, h, 0, tzinfo=ART)}

    scrapeadas = [r("a", 20, 16), r("b", 21, 12)]
    guardadas = [
        ("a", datetime(2026, 10, 20, 16, 0, tzinfo=ART)),        # sigue en la agenda
        ("reprogramada", datetime(2026, 10, 21, 10, 0, tzinfo=ART)),  # mismo día, ya no figura
        ("suspendida", datetime(2026, 10, 20, 15, 0, tzinfo=ART)),
        ("ya_paso", datetime(2026, 10, 20, 9, 0, tzinfo=ART)),   # hoy, pero antes de ahora
        ("otro_dia", datetime(2026, 10, 22, 10, 0, tzinfo=ART)), # día que la agenda no mostró
        # 02:00 UTC del 21 = 23:00 ART del 20: cuenta como día 20 (hora argentina).
        ("utc", datetime(2026, 10, 21, 2, 0, tzinfo=timezone.utc)),
    ]
    assert reuniones_a_dar_de_baja(guardadas, scrapeadas, ahora=ahora) == [
        "reprogramada", "suspendida", "utc",
    ]
    # Agenda vacía: no se borra nada.
    assert reuniones_a_dar_de_baja(guardadas, [], ahora=ahora) == []
