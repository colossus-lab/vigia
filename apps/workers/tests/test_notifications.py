"""Los emails (digest + invitación) deben escapar texto controlable por
usuario/terceros (nombre de workspace, quién invita, títulos de normas scrapeados)
para no permitir inyección de HTML/links en el cliente de correo."""
from vigia_workers.notifications import render_digest, render_invitation


def test_render_digest_escapes_user_controlled_html():
    items = [
        {
            "id": 1,
            "keyword": "<script>",
            "tipo": "Ley",
            "numero": "27000",
            "titulo": '<img src=x onerror=alert(1)>',
        }
    ]
    out = render_digest("<b>Acme & Co</b>", items)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "<img src=x" not in out
    assert "&lt;img" in out
    assert "&lt;b&gt;Acme &amp; Co&lt;/b&gt;" in out
    # el link legítimo a la norma sigue intacto
    assert "/norma/1" in out


def test_render_digest_pluraliza_coincidencias():
    item = {"id": 1, "keyword": "minería", "tipo": "Ley", "numero": "27000", "titulo": "T"}
    assert "Se detectó 1 coincidencia con tus alertas" in render_digest("WS", [item])
    out = render_digest("WS", [item, {**item, "id": 2}])
    assert "Se detectaron 2 coincidencias con tus alertas" in out


def test_render_invitation_escapes_user_controlled_html():
    accept_url = "https://vigia.openarg.org/auth/invite?token=abc123"
    out = render_invitation(
        "<b>WS</b>", "<i>admin</i>", accept_url, invited_by="<script>x</script>"
    )
    assert "<script>x</script>" not in out
    assert "&lt;script&gt;" in out
    assert "&lt;b&gt;WS&lt;/b&gt;" in out
    assert "&lt;i&gt;admin&lt;/i&gt;" in out
    # el accept_url legítimo NO debe romperse
    assert accept_url in out


def test_render_sin_creditos_escapa_el_nombre_del_workspace():
    from vigia_workers.notifications import render_sin_creditos

    out = render_sin_creditos("<b>Acme & Co</b>", "2026-09-01", "devops@colossuslab.org")
    assert "<b>Acme" not in out
    assert "&lt;b&gt;Acme &amp; Co&lt;/b&gt;" in out


def test_render_sin_creditos_dice_primero_lo_que_no_se_pierde():
    """El orden no es cosmético: si el mail arranca pidiendo plata se lee como
    un cobro. Primero que las alertas siguen andando, después el aporte."""
    from vigia_workers.notifications import render_sin_creditos

    out = render_sin_creditos("Acme", "2026-09-01", "devops@colossuslab.org")
    assert out.index("No perdiste nada") < out.index("/apoyar")
    # "Fundador" es vocabulario del proyecto hermano de Políticas Públicas y no
    # existe en /apoyar, donde los niveles son Colaborador/a y Patrocinador/a.
    assert "Fundador" not in out
    # y la salida sin pagar tiene que estar
    assert "el acceso no depende de poder pagar" in out
    assert "devops@colossuslab.org" in out
    # la fecha de renovación es lo que hace que la pausa no parezca definitiva
    assert "2026-09-01" in out
