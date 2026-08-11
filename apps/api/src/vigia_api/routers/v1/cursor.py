"""Cursores opacos para la paginación keyset de la API pública `/v1`.

Por qué keyset y no `offset`: el feed interno pagina con `LIMIT/OFFSET` y eso
alcanza para un usuario que mira tres pantallas, pero un integrador que quiere
bajar las ~533k normas paga un scan creciente por página (y el tope
`offset<=100000` le corta el recorrido a mitad de camino). Con keyset cada
página es un seek al índice: costo constante y sin techo.

El cursor es **opaco pero no secreto**: base64url de un JSON chico, sin firmar.
No hay nada que proteger adentro (una fecha y un id, ambos públicos), y firmarlo
obligaría a tener un secreto real configurado también en modo demo. Lo que sí se
valida con dureza son los tipos: el `k` se parsea como fecha/timestamp en el
router y el `i` tiene que ser un entero. Un cursor manipulado da 400, no una
página rara.

El **modo viaja adentro del cursor** a propósito. Los dos órdenes soportados
(`feed` = fecha_publicacion DESC, `sync` = updated_at ASC) recorren la tabla por
columnas distintas: pegar un cursor de uno en el otro saltearía filas en
silencio, que es justo el modo de falla que una API de sincronización no puede
tener. Si no coinciden, 400.
"""
from __future__ import annotations

import base64
import binascii
import json

from fastapi import HTTPException, status

# Listado editorial: fecha_publicacion DESC NULLS LAST, id DESC.
MODO_FEED = "feed"
# Sincronización incremental: updated_at ASC, id ASC.
MODO_SYNC = "sync"

_MODOS = (MODO_FEED, MODO_SYNC)

# Va en el payload para poder cambiar el formato sin romper a los clientes que
# tengan un cursor viejo guardado: un `v` desconocido da 400 con un detalle
# claro en vez de un KeyError.
_VERSION = 1


def _error(detalle: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detalle)


def encode(*, modo: str, clave: str | None, id_: int) -> str:
    """Arma el cursor que apunta a la última fila devuelta.

    `clave` es el valor de la columna de orden (ISO) o None para el tramo de
    normas sin `fecha_publicacion`; ver `routers/v1/normas.py`.
    """
    if modo not in _MODOS:  # pragma: no cover — error de programación, no de input
        raise ValueError(f"modo desconocido: {modo!r}")
    payload = {"v": _VERSION, "m": modo, "k": clave, "i": int(id_)}
    crudo = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    # Sin padding: los `=` finales obligan a url-encodear el cursor al pasarlo
    # como query param y todo el mundo se olvida una vez.
    return base64.urlsafe_b64encode(crudo).decode().rstrip("=")


def decode(cursor: str, *, modo_esperado: str) -> tuple[str | None, int]:
    """Devuelve `(clave, id)` del cursor, o 400 si no sirve para esta consulta."""
    relleno = "=" * (-len(cursor) % 4)
    try:
        crudo = base64.urlsafe_b64decode(cursor + relleno)
        payload = json.loads(crudo)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise _error("cursor_invalido") from exc
    if not isinstance(payload, dict):
        raise _error("cursor_invalido")
    if payload.get("v") != _VERSION:
        raise _error("cursor_de_version_desconocida")
    if payload.get("m") != modo_esperado:
        # El caso real: el cliente lista el feed, guarda el cursor y después
        # agrega `updated_since` reusándolo. Mejor un 400 explícito que un
        # recorrido que parece andar y se saltea filas.
        raise _error("cursor_de_otro_orden")
    clave = payload.get("k")
    if clave is not None and not isinstance(clave, str):
        raise _error("cursor_invalido")
    id_ = payload.get("i")
    # `isinstance(True, int)` es True en Python: los bool se descartan aparte.
    if not isinstance(id_, int) or isinstance(id_, bool):
        raise _error("cursor_invalido")
    return clave, id_
