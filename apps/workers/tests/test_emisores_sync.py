"""El catálogo de emisores tiene que ser el mismo en las tres copias.

La API valida las alertas contra `vigia_shared.constants.EMISORES` (no depende
de los conectores), la ingesta escribe `norma.emisor` con las claves de
`vigia_connectors.emisores`, y el web ofrece los chips desde
`apps/web/lib/constants.js`. Si divergen, o la API rechaza una clave real, o
acepta una alerta que nunca va a matchear nada, o el web no ofrece un regulador
(o manda uno que la API rechaza con 422).
"""
import re
from pathlib import Path

from vigia_connectors.emisores import EMISORES as EMISORES_INGESTA
from vigia_shared.constants import EMISORES as EMISORES_API

_WEB_CONSTANTS = Path(__file__).resolve().parents[3] / "apps" / "web" / "lib" / "constants.js"


def test_catalogos_de_emisores_coinciden():
    assert EMISORES_API == EMISORES_INGESTA


def test_el_web_ofrece_el_mismo_catalogo():
    js = _WEB_CONSTANTS.read_text(encoding="utf-8")
    bloque = re.search(r"export const EMISORES = \[(.*?)\];", js, re.S)
    assert bloque, "no se encontró EMISORES en apps/web/lib/constants.js"
    assert re.findall(r"clave: '([A-Z]+)'", bloque.group(1)) == EMISORES_API
