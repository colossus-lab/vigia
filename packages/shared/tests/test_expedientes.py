"""Normalización de expedientes (funciones puras, sin DB).

Es la llave del cruce entre votaciones, agenda y proyectos: si una forma no
normaliza, el cruce no falla, simplemente no encuentra nada. Cada caso de acá
es una forma vista en una fuente real.
"""
import pytest

from vigia_shared.expedientes import expedientes_de, extraer_expedientes, normalizar_expediente


@pytest.mark.parametrize(
    ("crudo", "canonico"),
    [
        # Diputados (CKAN proyectos-parlamentarios, agenda, BAT) — ya canónico.
        ("5330-D-2026", "5330-D-2026"),
        ("0014-JGM-2026", "0014-JGM-2026"),
        ("0010-PE-2026", "0010-PE-2026"),
        ("0032-S-2026", "0032-S-2026"),
        ("32-S-2026", "0032-S-2026"),
        # Senado: votaciones y agenda.
        ("PE-159/25-PL", "0159-PE-2025"),
        ("S-1042/26", "1042-S-2026"),
        ("PE 234/26", "0234-PE-2026"),
        ("S-842/10-PL", "0842-S-2010"),
        ("CD-12/26-PL", "0012-CD-2026"),
        ("CD-12/2026", "0012-CD-2026"),
        # Senado: external_id de senado_proyectos.
        ("1040/26-S-PL", "1040-S-2026"),
        ("1786/26-S-PC", "1786-S-2026"),
        ("159/25-PE-PL", "0159-PE-2025"),
        # Senado: path de verExp.
        ("159.25/PE/PL", "0159-PE-2025"),
        # Tolerancia de forma.
        ("  pe-159/25-pl ", "0159-PE-2025"),
        ("S-100/98", "0100-S-1998"),
    ],
)
def test_normaliza_las_formas_reales(crudo, canonico):
    assert normalizar_expediente(crudo) == canonico


@pytest.mark.parametrize(
    "crudo",
    [
        None,
        "",
        "HCDN182484",       # id interno de CKAN, no es expediente
        "1786/26",          # numero del Senado sin origen: ambiguo
        "LEY-27/20",        # origen fuera de la whitelist
        "DNU 70/23",
        "0000-D-2026",      # número cero
        "1234-D-1975",      # antes de 1983
        "PE-159/25 y S-1/26",  # dos expedientes: eso es extraer, no normalizar
        "1234-X-2026",
    ],
)
def test_rechaza_lo_que_no_es_un_expediente(crudo):
    assert normalizar_expediente(crudo) is None


def test_las_dos_camaras_terminan_en_la_misma_cadena():
    # El cruce entero depende de esto: la votación del Senado y el proyecto
    # ingestado por senado_proyectos tienen que dar exactamente lo mismo.
    assert (
        normalizar_expediente("PE-159/25-PL")
        == normalizar_expediente("159/25-PE-PL")
        == normalizar_expediente("159.25/PE/PL")
    )


def test_extrae_de_un_temario_libre():
    temario = (
        "Consideración de los proyectos de ley S-1042/26 (Mayans) y PE 234/26 "
        "sobre presupuesto; expte. 0032-S-2026 en revisión. Ley 27/20. Res. 5/26."
    )
    assert extraer_expedientes(temario) == ["1042-S-2026", "0234-PE-2026", "0032-S-2026"]


def test_extrae_sin_repetir_y_en_orden():
    assert extraer_expedientes("S-1/26, s-1/26 y 0001-S-2026; luego PE-2/26") == [
        "0001-S-2026",
        "0002-PE-2026",
    ]


def test_no_extrae_pegado_a_otra_palabra():
    # "PS-12/26" no es "S-12/26", y un número más largo no es otro expediente.
    assert extraer_expedientes("PS-12/26") == []
    assert extraer_expedientes("ref. 15330-D-2026") == ["15330-D-2026"]


def test_extraer_texto_vacio():
    assert extraer_expedientes(None) == []
    assert extraer_expedientes("Reunión informativa con el ministro") == []


def test_expedientes_de_varios_campos():
    assert expedientes_de("0010-PE-2026", None, "CD-12/26", "0010-PE-2026") == [
        "0010-PE-2026",
        "0012-CD-2026",
    ]
    assert expedientes_de(None, "NA", "") == []
