"""Expedientes del Congreso: una sola forma canónica para cruzar las dos cámaras.

El mismo expediente se escribe distinto según quién lo cite, y el cruce entre
votaciones, agenda de comisiones y proyectos depende de que todos terminen en
la misma cadena. Si la normalización falla, el cruce no da error: simplemente
no encuentra nada. Por eso todo pasa por acá y está testeado caso por caso.

Formas que circulan (verificadas contra prod y los sitios, 2026-10):

- Diputados (CKAN, agenda, BAT): ``5330-D-2026``, ``0014-JGM-2026``, ``0032-S-2026``
- Senado, votaciones y agenda: ``PE-159/25-PL``, ``S-1042/26``, ``PE 234/26``
- Senado, external_id de `senado_proyectos`: ``1040/26-S-PL``
- Senado, links `verExp`: ``159.25/PE/PL``

Forma canónica: ``NNNN-ORIGEN-AAAA`` (número con ceros a la izquierda hasta 4
dígitos, origen en mayúsculas, año de 4 dígitos), que es la de Diputados. El
sufijo de tipo del Senado (``-PL``, ``-PR``...) se descarta: el número + origen
+ año ya identifica el expediente.

Ojo: un proyecto tiene un expediente **por cámara** (el que entra por Diputados
como ``0010-PE-2026`` pasa al Senado con otro número y origen ``CD``). Por eso
`norma.expedientes` es un array y el cruce es por solapamiento (``&&``).
"""
from __future__ import annotations

import re

# Orígenes válidos. Lista cerrada a propósito: en el temario libre de una
# reunión aparece "Ley 27/20" o "Res. 5/26", y sin whitelist eso se leería
# como expediente.
#   D: Diputados · S: Senado · CD: venido de Diputados (numeración del Senado)
#   PE: Poder Ejecutivo · JGM: Jefatura de Gabinete · OV: oficiales varios
#   P: particulares
ORIGENES = ("JGM", "CD", "PE", "OV", "D", "S", "P")
_ORIG = "|".join(ORIGENES)  # los largos primero: "CD" antes que "D"

# Sufijo de tipo que el Senado agrega al final y que descartamos.
_TIPO = r"(?:-[A-Z]{2})?(?![A-Z])"

_PATRONES = (
    # 5330-D-2026 · 0032-S-2026 · 14-JGM-26
    re.compile(rf"(?P<num>\d{{1,5}})-(?P<orig>{_ORIG})-(?P<anio>\d{{4}}|\d{{2}})(?![\d/])"),
    # PE-159/25-PL · S-1042/26 · PE 234/26 · CD-12/2026
    re.compile(rf"(?P<orig>{_ORIG})[-\s](?P<num>\d{{1,5}})/(?P<anio>\d{{4}}|\d{{2}})(?!\d){_TIPO}"),
    # 1040/26-S-PL (external_id de senado_proyectos)
    re.compile(rf"(?P<num>\d{{1,5}})/(?P<anio>\d{{4}}|\d{{2}})-(?P<orig>{_ORIG}){_TIPO}"),
    # 159.25/PE/PL (path de verExp)
    re.compile(rf"(?P<num>\d{{1,5}})\.(?P<anio>\d{{4}}|\d{{2}})/(?P<orig>{_ORIG})(?:/[A-Z]{{2}})?"),
)

# Borde izquierdo: que no esté pegado a otra letra/dígito ("XS-12/26", "15330-D-2026").
_ANTES = re.compile(r"[A-Z0-9]")

_PRIMER_ANIO = 1983  # retorno de la democracia; el Senado tiene actas desde ahí


def _anio(s: str) -> int | None:
    n = int(s)
    if len(s) == 2:
        # Pivote en 50: "25" → 2025, "98" → 1998. Alcanza hasta 2050.
        n += 2000 if n <= 50 else 1900
    return n if _PRIMER_ANIO <= n <= 2099 else None


def _canonico(m: re.Match[str]) -> str | None:
    anio = _anio(m["anio"])
    num = int(m["num"])
    if anio is None or num == 0:
        return None
    return f"{num:04d}-{m['orig']}-{anio}"


def normalizar_expediente(s: str | None) -> str | None:
    """Devuelve la forma canónica de UN expediente, o None si no lo es.

    Exige que la cadena entera sea el expediente (salvo espacios): para buscar
    expedientes dentro de un texto libre está `extraer_expedientes`.
    """
    if not s:
        return None
    t = s.strip().upper()
    for pat in _PATRONES:
        m = pat.fullmatch(t)
        if m:
            return _canonico(m)
    return None


def extraer_expedientes(texto: str | None) -> list[str]:
    """Todos los expedientes citados en un texto libre, canónicos y sin repetir.

    Mantiene el orden de aparición (el primero suele ser el principal).
    """
    if not texto:
        return []
    t = texto.upper()
    vistos: dict[str, tuple[int, int]] = {}
    ocupado: list[tuple[int, int]] = []
    for pat in _PATRONES:
        for m in pat.finditer(t):
            ini, fin = m.span()
            if ini > 0 and _ANTES.match(t[ini - 1]):
                continue
            # Un mismo tramo puede matchear dos patrones; gana el primero.
            if any(ini < f and fin > i for i, f in ocupado):
                continue
            exp = _canonico(m)
            if exp and exp not in vistos:
                vistos[exp] = (ini, fin)
                ocupado.append((ini, fin))
    return sorted(vistos, key=lambda e: vistos[e][0])


def expedientes_de(*valores: str | None) -> list[str]:
    """Canónicos y sin repetir de varios campos sueltos (p.ej. EXP_DIPUTADOS + EXP_SENADO)."""
    out: list[str] = []
    for v in valores:
        e = normalizar_expediente(v)
        if e and e not in out:
            out.append(e)
    return out
