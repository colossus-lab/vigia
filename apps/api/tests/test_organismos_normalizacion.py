"""Normalización del `organismo` para rankear (stats/organismos).

Dos cosas que se rompen fácil y por eso están fijadas acá:

1. Variantes de la MISMA entidad tienen que agrupar (mayúsculas, guión colgado,
   espacios de más). En producción había 14 grupos partidos, 44.479 normas:
   `Jefatura de Gabinete de Ministros` y `JEFATURA DE GABINETE DE MINISTROS`
   sumaban por separado 32.175 entre las dos.

2. Entidades DISTINTAS no tienen que fusionarse. Hay un MINISTERIO DE SALUD
   nacional, uno de CABA y uno de PBA: normalizar solo por nombre haría que el
   ranking mienta al revés, que es peor que el bug original.
"""
from __future__ import annotations

import pytest

from vigia_shared.organismos import clave_organismo


# --- agrupan: misma entidad escrita distinto ------------------------------


@pytest.mark.parametrize(
    "a,b,juris,por_que",
    [
        ("Ministerio de Salud", "Ministerio de Salud-", "CABA", "guión colgado del scraping"),
        ("Jefatura de Gabinete de Ministros", "JEFATURA DE GABINETE DE MINISTROS", "Nacional", "mayúsculas"),
        ("SECRETARIA DE EMPLEO PUBLICO", "SECRETARIA DE EMPLEO PUBLICO -", "Nacional", "guión con espacio"),
        ("Ministerio de Defensa", "  Ministerio   de   Defensa  ", "Nacional", "espacios de más"),
        ("Ministerio de Transporte", "Ministerio de Transporte.", "Nacional", "punto final"),
    ],
)
def test_variantes_de_la_misma_entidad_agrupan(a, b, juris, por_que):
    assert clave_organismo(a, juris) == clave_organismo(b, juris), por_que


# --- NO agrupan: entidades distintas --------------------------------------


def test_el_mismo_ministerio_de_distinta_jurisdiccion_no_se_fusiona():
    nacion = clave_organismo("MINISTERIO DE SALUD", "Nacional")
    caba = clave_organismo("Ministerio de Salud", "CABA")
    pba = clave_organismo("MINISTERIO DE SALUD", "Buenos Aires")
    assert len({nacion, caba, pba}) == 3, "se fusionaron ministerios de jurisdicciones distintas"


def test_organismos_realmente_distintos_no_agrupan():
    assert clave_organismo("Ministerio de Salud", "CABA") != clave_organismo(
        "Ministerio de Hacienda y Finanzas", "CABA"
    )
    # Un sub-organismo NO es su ministerio: se cuentan aparte a propósito, porque
    # fusionarlos requeriría decidir jerarquías y eso es otra discusión.
    assert clave_organismo("MINISTERIO DE SALUD", "Nacional") != clave_organismo(
        "MINISTERIO DE SALUD - SECRETARÍA DE GESTIÓN SANITARIA", "Nacional"
    )


# --- entradas degeneradas --------------------------------------------------


@pytest.mark.parametrize("valor", [None, "", "   ", "-", "---", " . "])
def test_sin_organismo_util_devuelve_none(valor):
    assert clave_organismo(valor, "Nacional") is None


def test_sin_jurisdiccion_no_explota():
    assert clave_organismo("ANMAT", None) == ("", "ANMAT")
