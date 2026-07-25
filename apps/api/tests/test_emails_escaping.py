"""Regresión: el HTML de los emails debe escapar todo lo que elige el usuario.

Este test existe porque el módulo de mail de la API nació como fork del de
workers y quedó SIN escapar. El `workspace_name` lo elige quien crea el
workspace, y el mail sale firmado con el DKIM de openarg.org: sin escapado,
cualquiera podía meter un `<a>` con los estilos de Vigía en un mail que para el
destinatario venía, legítimamente, de nosotros.

No alcanza con buscar substrings: `x" onmouseover="alert(1)` deja el texto
`onmouseover=` en la salida aunque esté perfectamente escapado. Por eso se
parsea el HTML y se mira qué etiquetas y atributos REALES quedaron.
"""
from html.parser import HTMLParser

import pytest

from vigia_api.services.emails import render_invitation

# Etiquetas que arma la plantilla. Cualquier otra solo puede venir del input.
TAGS_PLANTILLA = {"div", "p", "h2", "em", "strong", "a"}

PAYLOADS = [
    "Equipo</em></h2><a href='https://falso.example'>Verifica tu cuenta</a><h2><em>",
    '<script>fetch("https://malo.example")</script>',
    '<img src="https://malo.example/pixel.gif">',
    "<iframe src='https://malo.example'></iframe>",
]

# `workspace_name` e `invited_by` caen en posición de TEXTO, donde una comilla
# suelta no rompe nada. El único valor que cae dentro de un atributo es la URL,
# en `href="…"`, y ahí sí escapar las comillas es lo que importa. Hoy la arma el
# servidor a partir de un token generado con `secrets`, así que esto es defensa
# en profundidad, no un agujero abierto: cubre el día que la URL venga de afuera.
PAYLOAD_ATRIBUTO = 'https://vigia.openarg.org/x" onmouseover="alert(1)'


class _Inspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: list[str] = []
        self.attrs: list[tuple[str, str, str | None]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        for k, v in attrs:
            self.attrs.append((tag, k, v))


def _inspeccionar(html: str) -> _Inspector:
    p = _Inspector()
    p.feed(html)
    return p


@pytest.mark.parametrize("payload", PAYLOADS)
def test_workspace_name_no_inyecta_html(payload):
    p = _inspeccionar(
        render_invitation(payload, "admin", "https://vigia.openarg.org/auth/invite?token=t")
    )
    assert not set(p.tags) - TAGS_PLANTILLA, "el input creó etiquetas nuevas"
    assert not [k for _, k, _ in p.attrs if k.startswith("on")], "quedó un handler de evento"
    assert not [
        v for _, k, v in p.attrs if k == "href" and v and "vigia.openarg.org" not in v
    ], "quedó un link a un dominio ajeno"


@pytest.mark.parametrize("payload", PAYLOADS)
def test_invited_by_no_inyecta_html(payload):
    p = _inspeccionar(
        render_invitation(
            "Equipo", "admin", "https://vigia.openarg.org/auth/invite?token=t", invited_by=payload
        )
    )
    assert not set(p.tags) - TAGS_PLANTILLA
    assert not [k for _, k, _ in p.attrs if k.startswith("on")]


def test_la_url_no_escapa_de_su_atributo():
    p = _inspeccionar(render_invitation("Equipo", "admin", PAYLOAD_ATRIBUTO))
    assert not [k for _, k, _ in p.attrs if k.startswith("on")], "la URL creó un handler de evento"


def test_el_texto_legitimo_sigue_saliendo_legible():
    # El escapado no debe romper nombres normales con acentos y ampersands.
    html = render_invitation(
        "Estudio Pérez & Asociados", "viewer", "https://vigia.openarg.org/auth/invite?token=t"
    )
    assert "Estudio Pérez &amp; Asociados" in html
    assert "viewer" in html


def test_api_y_workers_comparten_el_mismo_escapador():
    # La causa raíz del bug fue el fork: si vuelven a divergir, esto falla.
    from vigia_shared.emails_html import esc
    from vigia_workers.notifications import _esc as esc_workers

    assert esc_workers is esc
