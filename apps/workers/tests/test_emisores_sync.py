"""El catálogo de emisores de la API tiene que ser el mismo que escribe la ingesta.

La API valida las alertas contra `vigia_shared.constants.EMISORES` (no depende
de los conectores), y la ingesta escribe `norma.emisor` con las claves de
`vigia_connectors.emisores`. Si divergen, o la API rechaza una clave real, o
acepta una alerta que nunca va a matchear nada.
"""
from vigia_connectors.emisores import EMISORES as EMISORES_INGESTA
from vigia_shared.constants import EMISORES as EMISORES_API


def test_catalogos_de_emisores_coinciden():
    assert EMISORES_API == EMISORES_INGESTA
