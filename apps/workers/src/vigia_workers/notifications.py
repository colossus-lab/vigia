"""Envío de email via Resend (HTTP API). No-op limpio si falta RESEND_API_KEY.

La key vive SOLO en el entorno (.env del EC2 / Secrets Manager) — nunca en el
repo. Dominio `openarg.org` verificado en Resend (DKIM/SPF en Route53).
"""
from __future__ import annotations

import os

import httpx

# El escapador vive en vigia_shared para que la API y los workers usen el mismo:
# esta función existía solo acá, y el módulo de mail de la API —que nació como
# fork de este— quedó sin ella durante meses.
from vigia_shared.emails_html import esc as _esc

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
ALERTS_FROM_EMAIL = os.environ.get("ALERTS_FROM_EMAIL", "Vigía <alertas@openarg.org>")
WEB_BASE_URL = os.environ.get("WEB_BASE_URL", "https://vigia.openarg.org").rstrip("/")
RESEND_URL = "https://api.resend.com/emails"


def send_email(*, to: str, subject: str, html: str) -> dict:
    """Envía un email. Si no hay API key, loguea y devuelve {'skipped': True}."""
    if not RESEND_API_KEY:
        print(f"[notifications] (sin RESEND_API_KEY) email a {to}: {subject}")
        return {"skipped": True, "to": to}
    try:
        resp = httpx.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": ALERTS_FROM_EMAIL, "to": [to], "subject": subject, "html": html},
            timeout=15.0,
        )
        resp.raise_for_status()
        return {"sent": True, "to": to, "id": resp.json().get("id")}
    except Exception as exc:  # pragma: no cover
        print(f"[notifications] error enviando a {to}: {exc!r}")
        return {"error": str(exc), "to": to}


def render_digest(workspace_name: str, items: list[dict]) -> str:
    """HTML del digest de alertas, con link al detalle de cada norma."""
    rows = "".join(
        f'<tr><td style="padding:10px 0;border-bottom:1px solid #1f2937">'
        f'<p style="margin:0 0 2px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#74ACDF">'
        f'{_esc(i["keyword"])} · {_esc(i["tipo"])} {_esc(i.get("numero") or "")}</p>'
        f'<a href="{WEB_BASE_URL}/norma/{int(i["id"])}" '
        f'style="color:#E8ECF4;font-size:14px;font-weight:600;text-decoration:none">{_esc(i["titulo"])}</a>'
        f"</td></tr>"
        if i.get("id")
        else f'<tr><td style="padding:10px 0;border-bottom:1px solid #1f2937">'
        f'<p style="margin:0;color:#E8ECF4;font-size:14px"><strong>{_esc(i["keyword"])}</strong> — '
        f'{_esc(i["tipo"])} {_esc(i.get("numero") or "")}: {_esc(i["titulo"])}</p></td></tr>'
        for i in items
    )
    detectadas = (
        "Se detectó 1 coincidencia"
        if len(items) == 1
        else f"Se detectaron {len(items)} coincidencias"
    )
    return (
        f'<div style="font-family:Inter,system-ui,sans-serif;background:#06090F;color:#E8ECF4;'
        f'padding:32px 24px;border-radius:12px;max-width:600px">'
        f'<p style="margin:0 0 4px;font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#636E85">'
        f"VIGÍA / ALERTAS</p>"
        f'<h2 style="margin:0 0 6px;font-size:20px;color:#E8ECF4">Nuevas normas para '
        f'<em style="color:#F6B40E;font-style:italic">{_esc(workspace_name)}</em></h2>'
        f'<p style="margin:0 0 18px;font-size:13px;color:#8892A8">'
        f"{detectadas} con tus alertas:</p>"
        f'<table style="width:100%;border-collapse:collapse">{rows}</table>'
        f'<p style="margin:20px 0 0;font-size:12px"><a href="{WEB_BASE_URL}/alerts" '
        f'style="color:#74ACDF;text-decoration:none">Gestionar mis alertas →</a></p>'
        f'<p style="margin:14px 0 0;color:#636E85;font-size:11px">Inteligencia legislativa · Colossus Lab</p>'
        f"</div>"
    )


def render_invitation(
    workspace_name: str, role: str, accept_url: str, invited_by: str | None = None
) -> str:
    """HTML del email de invitación a un workspace."""
    inviter = f" por <strong>{_esc(invited_by)}</strong>" if invited_by else ""
    return (
        f'<div style="font-family:Inter,system-ui,sans-serif;background:#06090F;color:#E8ECF4;'
        f'padding:32px 24px;border-radius:12px;max-width:600px">'
        f'<p style="margin:0 0 4px;font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#636E85">'
        f"VIGÍA / INVITACIÓN</p>"
        f'<h2 style="margin:0 0 10px;font-size:20px;color:#E8ECF4">Te invitaron a '
        f'<em style="color:#F6B40E;font-style:italic">{_esc(workspace_name)}</em></h2>'
        f'<p style="margin:0 0 22px;font-size:13px;color:#8892A8;line-height:1.6">'
        f"Fuiste invitado{inviter} a sumarte como <strong>{_esc(role)}</strong> al workspace "
        f"<strong>{_esc(workspace_name)}</strong> en Vigía, la plataforma de inteligencia "
        f"legislativa y regulatoria argentina.</p>"
        f'<a href="{accept_url}" style="display:inline-block;background:#74ACDF;color:#06090F;'
        f'font-weight:700;font-size:14px;padding:10px 22px;border-radius:999px;text-decoration:none">'
        f"Aceptar invitación</a>"
        f'<p style="margin:18px 0 0;font-size:11px;color:#636E85">Si el botón no funciona, '
        f'abrí este link: <a href="{accept_url}" style="color:#74ACDF">{accept_url}</a></p>'
        f'<p style="margin:14px 0 0;color:#636E85;font-size:11px">Inteligencia legislativa · Colossus Lab</p>'
        f"</div>"
    )


def render_sin_creditos(workspace_name: str, renueva: str, contacto: str) -> str:
    """HTML del aviso de "te quedaste sin créditos".

    El orden es deliberado: primero lo que NO se pierde (las alertas siguen
    registrando y está todo en la app), después cómo se sigue, y al final la
    salida sin pagar. Al revés se lee como un cobro.

    Sale UNA vez por período — la marca la lleva `credito_contador`.
    """
    return (
        f'<div style="font-family:Inter,system-ui,sans-serif;background:#06090F;color:#E8ECF4;'
        f'padding:32px 24px;border-radius:12px;max-width:600px">'
        f'<p style="margin:0 0 4px;font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#636E85">'
        f"VIGÍA / CRÉDITOS</p>"
        f'<h2 style="margin:0 0 10px;font-size:20px;color:#E8ECF4">Se te acabaron los créditos de '
        f'<em style="color:#F6B40E;font-style:italic">{_esc(workspace_name)}</em></h2>'
        f'<p style="margin:0 0 16px;font-size:13px;color:#8892A8;line-height:1.6">'
        f"<strong style=\"color:#E8ECF4\">No perdiste nada.</strong> Tus alertas siguen "
        f"funcionando y registrando cada norma que coincide: está todo en Vigía, esperándote. "
        f"Lo único que se pausó son estos mails.</p>"
        f'<p style="margin:0 0 22px;font-size:13px;color:#8892A8;line-height:1.6">'
        f"Los créditos se renuevan el <strong style=\"color:#E8ECF4\">{_esc(renueva)}</strong> "
        f"y volvés a recibirlos automáticamente.</p>"
        f'<a href="{WEB_BASE_URL}/alerts" style="display:inline-block;background:#74ACDF;color:#06090F;'
        f'font-weight:700;font-size:14px;padding:10px 22px;border-radius:999px;text-decoration:none">'
        f"Ver lo que se detectó</a>"
        f'<p style="margin:22px 0 0;font-size:13px;color:#8892A8;line-height:1.6">'
        f"¿Querés seguir recibiéndolos ahora? Quienes sostienen Vigía con un aporte mensual "
        f"recargan cada quincena o trabajan sin cupo: "
        f'<a href="{WEB_BASE_URL}/apoyar" style="color:#74ACDF;text-decoration:none">'
        f"apoyá el proyecto</a>.</p>"
        f'<p style="margin:14px 0 0;font-size:13px;color:#8892A8;line-height:1.6">'
        f"Y si no podés aportar, escribinos igual a "
        f'<a href="mailto:{_esc(contacto)}" style="color:#74ACDF;text-decoration:none">{_esc(contacto)}</a>: '
        f"el acceso no depende de poder pagar.</p>"
        f'<p style="margin:20px 0 0;color:#636E85;font-size:11px">Inteligencia legislativa · Colossus Lab</p>'
        f"</div>"
    )
