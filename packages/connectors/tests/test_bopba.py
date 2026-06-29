"""Tests del conector BO PBA: segmentación del PDF OFICIAL (texto extraído)."""
from __future__ import annotations

from datetime import date

from vigia_connectors.bopba import parse_edicion_fecha, parse_oficial

# Texto representativo de lo que pypdf extrae de la sección OFICIAL: masthead,
# marcadores ◢ de rubro, organismo en mayúsculas, header TIPO N°, dateline,
# VISTO, una CITA en prosa (no debe matchear) y un rubro societario (se saltea).
SAMPLE = """AÑO CXVII - Nº 30268
La Plata, lunes 29 de junio de 2026.-
AUTORIDADES
Gobernador Dr. Axel Kicillof
◢
RESOLUCIONES
MINISTERIO DE INFRAESTRUCTURA Y SERVICIOS PÚBLICOS
RESOLUCIÓN N° 502-MIYSPGP-2026
LA PLATA, BUENOS AIRES
Lunes 22 de Junio de 2026
VISTO el EX-2025-16115268-GDEBA-DPTLMIYSPGP mediante el cual tramita la Licitación Pública N° 58/25 para la obra, y
CONSIDERANDO:
Que mediante Resolución N° 1113/25 del Ministro se aprobó la documentación (esto es una cita en prosa).
◢
RESOLUCIONES FIRMA CONJUNTA
DIRECCIÓN GENERAL DE CULTURA Y EDUCACIÓN
RESOLUCIÓN FIRMA CONJUNTA N° 2762-DGCYE-2026
LA PLATA, BUENOS AIRES
Jueves 18 de Junio de 2026
VISTO el expediente EX-2026-1-GDEBA por el cual se aprueba el calendario escolar 2026, y
CONSIDERANDO:
◢
SOCIEDADES
ACME SOCIEDAD ANONIMA
Por 5 días. Constitución. Acta del 1 de junio. (esto NO es norma)
"""


def test_segmenta_solo_normas():
    normas = parse_oficial(SAMPLE, fecha=None, url="https://bo.gba/secciones/14246/ver")
    # 2 actos reales (resolución + firma conjunta); la cita en prosa y el rubro
    # SOCIEDADES no generan normas.
    assert [n.numero for n in normas] == ["502-MIYSPGP-2026", "2762-DGCYE-2026"]
    assert all(n.tipo == "RESOLUCION" for n in normas)
    assert all(n.fecha == date(2026, 6, 29) for n in normas)  # fecha del masthead
    assert all(n.url.endswith("/secciones/14246/ver") for n in normas)

    r0 = normas[0]
    assert r0.organismo == "MINISTERIO DE INFRAESTRUCTURA Y SERVICIOS PÚBLICOS"
    assert r0.rubro == "RESOLUCIONES"
    # El prefijo "el EX-… mediante el cual" se limpia → arranca en el asunto.
    assert r0.titulo.startswith("Tramita la Licitación")

    assert normas[1].rubro == "RESOLUCIONES FIRMA CONJUNTA"
    assert normas[1].organismo == "DIRECCIÓN GENERAL DE CULTURA Y EDUCACIÓN"


def test_parse_edicion_fecha():
    assert parse_edicion_fecha("La Plata, lunes 29 de junio de 2026.-") == date(2026, 6, 29)
    assert parse_edicion_fecha("La Plata, jueves 2 de octubre de 2025") == date(2025, 10, 2)
    assert parse_edicion_fecha("sin fecha") is None
