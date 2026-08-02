"""Normalización del `organismo` para agrupar y rankear.

El `organismo` es texto libre que viene de cada fuente, y la misma entidad llega
escrita distinto: `Jefatura de Gabinete de Ministros` y `JEFATURA DE GABINETE DE
MINISTROS` son la misma y sumaban por separado — 32.175 normas partidas en dos.
Otras traen un guión colgado del scraping (`Ministerio de Salud-`).

OJO — la clave incluye la JURISDICCIÓN a propósito. Hay un `MINISTERIO DE SALUD`
nacional, uno de CABA y uno de PBA, y son entidades **distintas**: normalizar solo
por nombre las fusionaría y el ranking mentiría al revés.

Esto NO reemplaza a `emisores.detect_emisor`, que resuelve otro problema: mapear a
una clave canónica corta un puñado de reguladores nacionales muy consultados
(ARCA, BCRA, ENACOM…), incluidos los renombres (AFIP→ARCA). Acá no hay catálogo:
se limpia lo que venga, sea quien sea.

La misma expresión existe en SQL dentro de `stats.organismos` para poder agrupar
sin backfillear una columna nueva; si se tocan las reglas, hay que tocar las dos.
"""
from __future__ import annotations

import re

# Basura de scraping al final del nombre: guiones, dos puntos, comas, puntos.
_COLA = re.compile(r"[\s\-–—:;,\.]+$")
_ESPACIOS = re.compile(r"\s+")


def clave_organismo(organismo: str | None, jurisdiccion: str | None) -> tuple[str, str] | None:
    """Clave estable para agrupar: (jurisdicción, nombre normalizado).

    Devuelve None si no hay organismo con el que trabajar.
    """
    if not organismo or not organismo.strip():
        return None
    limpio = _ESPACIOS.sub(" ", organismo).strip()
    limpio = _COLA.sub("", limpio).strip()
    if not limpio:
        return None
    return ((jurisdiccion or "").strip(), limpio.upper())
