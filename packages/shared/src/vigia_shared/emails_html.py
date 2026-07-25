"""Escapado de HTML para los emails, compartido por la API y los workers.

Vive acá y no en cada app a propósito. El módulo de mail de la API nació como
fork del de workers y quedó SIN escapar: el nombre del workspace —texto que
elige el usuario— se interpolaba crudo en el HTML, así que cualquiera podía
inyectar un `<a>` con estilo de Vigía en un mail firmado con el DKIM de
openarg.org. Phishing con nuestra propia firma.

Un solo escapador para los dos lados evita que el fork vuelva a divergir.
"""
from __future__ import annotations

import html


def esc(value) -> str:
    """Escapa texto controlable por usuario/terceros antes de interpolarlo en HTML.

    `html.escape` con `quote=True` (el default) también escapa comillas, así que
    sirve tanto para el cuerpo como para el valor de un atributo (`href="…"`).
    """
    return html.escape(str(value)) if value is not None else ""
