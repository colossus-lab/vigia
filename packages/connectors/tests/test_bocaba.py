"""Tests del conector BO CABA: aplanado del árbol, mapeo de tipos y filtrado."""
from __future__ import annotations

from datetime import date

from vigia_connectors.bocaba import (
    _map_tipo,
    _parse_fecha,
    _parse_numero,
    parse_boletin,
)

# Recorte mínimo con la forma real de /obtenerBoletin/{fecha}/true:
# normas anidadas Poder -> Tipo -> Organismo -> [norma].
SAMPLE = {
    "boletin": {"fecha_publicacion": "29/06/2026", "numero": 7397},
    "normas": {
        "normas": {
            "Poder Legislativo": {
                "Ley": {
                    "Legislatura de la Ciudad de Buenos Aires": [
                        {
                            "nombre": "Ley N° 6960",
                            "sumario": "Autoriza al Poder Ejecutivo a contraer empréstitos.",
                            "id_norma": 984192,
                            "url_norma": "http://api/download/5165246",
                        }
                    ]
                }
            },
            "Poder Ejecutivo": {
                "Resolución": {
                    "Ministerio de Salud": [
                        {
                            "nombre": "Resolución N° 182/2026",
                            "sumario": "Renueva Certificado de Aptitud Ambiental.",
                            "id_norma": 984149,
                            "url_norma": "http://api/download/5165200",
                        }
                    ]
                },
                "Disposición": {
                    "Ministerio de Salud": [
                        {"nombre": "Disposición N° 7", "sumario": "Aprueba pliego.", "id_norma": 984000}
                    ]
                },
            },
            # Las dos categorías siguientes son avisos: deben ignorarse.
            "Edictos Oficiales": {
                "Citación": {"Juzgado": [{"nombre": "Citación", "sumario": "Cita.", "id_norma": 999999}]}
            },
            "Licitaciones": {
                "Licitación Pública": {
                    "Ministerio de Salud": [{"nombre": "Licitación N° 1", "sumario": "x", "id_norma": 888888}]
                }
            },
        }
    },
}


def test_parse_filtra_avisos_y_mapea():
    normas = parse_boletin(SAMPLE, date(2026, 6, 29))
    # 3 actos normativos; edictos y licitaciones quedan fuera.
    assert sorted(n.external_id for n in normas) == ["984000", "984149", "984192"]
    by_id = {n.external_id: n for n in normas}

    ley = by_id["984192"]
    assert ley.tipo == "LEY"
    assert ley.numero == "6960"
    assert ley.fecha == date(2026, 6, 29)
    assert ley.titulo.startswith("Autoriza al Poder Ejecutivo")
    assert ley.url == "http://api/download/5165246"

    assert by_id["984149"].tipo == "RESOLUCION"
    assert by_id["984149"].numero == "182/2026"
    assert by_id["984000"].tipo == "DISPOSICION"
    assert by_id["984000"].numero == "7"
    assert by_id["984000"].url is None


def test_map_tipo():
    assert _map_tipo("Ley") == "LEY"
    assert _map_tipo("Resolución Comunal") == "RESOLUCION"
    assert _map_tipo("Resolución de Directorio") == "RESOLUCION"
    assert _map_tipo("Disposición") == "DISPOSICION"
    assert _map_tipo("Acordada") == "OTRA"
    assert _map_tipo("Acta") == "OTRA"


def test_parse_numero_y_fecha():
    assert _parse_numero("Decreto N° 234") == "234"
    assert _parse_numero("Resolución N° 182/GCABA") == "182"  # corta en la letra, sin barra colgando
    assert _parse_numero("Sin numero") is None
    assert _parse_fecha("29/06/2026") == date(2026, 6, 29)
    assert _parse_fecha("29-06-2026") == date(2026, 6, 29)
    assert _parse_fecha(None) is None


def test_parse_boletin_vacio():
    assert parse_boletin({}, date(2026, 6, 29)) == []
    assert parse_boletin({"boletin": {}, "normas": {}}, date(2026, 6, 29)) == []
