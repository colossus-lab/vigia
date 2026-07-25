"""Emails transaccionales de la API (invitaciones) vía Resend.

Mismo patrón que vigia_workers.notifications: no-op limpio sin RESEND_API_KEY
(la key vive solo en el entorno, nunca en el repo). El envío es best-effort:
una invitación se crea igual aunque el email falle — el link compartible por
WhatsApp/copia es el camino principal.
"""
from __future__ import annotations

import os

import httpx

from vigia_shared.emails_html import esc

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
ALERTS_FROM_EMAIL = os.environ.get("ALERTS_FROM_EMAIL", "Vigía <alertas@openarg.org>")
WEB_BASE_URL = os.environ.get("WEB_BASE_URL", "https://vigia.openarg.org").rstrip("/")
RESEND_URL = "https://api.resend.com/emails"


def invite_accept_url(token: str) -> str:
    return f"{WEB_BASE_URL}/auth/invite?token={token}"


def render_invitation(
    workspace_name: str, role: str, accept_url: str, invited_by: str | None = None
) -> str:
    # TODO lo interpolado va escapado: `workspace_name` e `invited_by` los elige
    # el usuario, y el mail sale firmado con el DKIM de openarg.org.
    inviter = f" por <strong>{esc(invited_by)}</strong>" if invited_by else ""
    url = esc(accept_url)
    return (
        f'<div style="font-family:Inter,system-ui,sans-serif;background:#06090F;color:#E8ECF4;'
        f'padding:32px 24px;border-radius:12px;max-width:600px">'
        f'<p style="margin:0 0 4px;font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#636E85">'
        f"VIGÍA / INVITACIÓN</p>"
        f'<h2 style="margin:0 0 10px;font-size:20px;color:#E8ECF4">Te invitaron a '
        f'<em style="color:#F6B40E;font-style:italic">{esc(workspace_name)}</em></h2>'
        f'<p style="margin:0 0 22px;font-size:13px;color:#8892A8;line-height:1.6">'
        f"Fuiste invitado{inviter} a sumarte como <strong>{esc(role)}</strong> al workspace "
        f"<strong>{esc(workspace_name)}</strong> en Vigía, la plataforma de inteligencia "
        f"legislativa y regulatoria argentina.</p>"
        f'<a href="{url}" style="display:inline-block;background:#74ACDF;color:#06090F;'
        f'font-weight:700;font-size:14px;padding:10px 22px;border-radius:999px;text-decoration:none">'
        f"Aceptar invitación</a>"
        f'<p style="margin:18px 0 0;font-size:11px;color:#636E85">Si el botón no funciona, '
        f'abrí este link: <a href="{url}" style="color:#74ACDF">{url}</a></p>'
        f'<p style="margin:14px 0 0;color:#636E85;font-size:11px">Inteligencia legislativa · Colossus Lab</p>'
        f"</div>"
    )


async def send_invitation_email(
    *, to: str, workspace_name: str, role: str, token: str, invited_by: str | None = None
) -> dict:
    """Manda el email de invitación. No-op sin key; nunca levanta excepción."""
    if not RESEND_API_KEY:
        print(f"[emails] (sin RESEND_API_KEY) invitación a {to} para {workspace_name}")
        return {"skipped": True, "to": to}
    accept_url = invite_accept_url(token)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                json={
                    "from": ALERTS_FROM_EMAIL,
                    "to": [to],
                    "subject": f"Te invitaron a {workspace_name} en Vigía",
                    "html": render_invitation(workspace_name, role, accept_url, invited_by),
                },
            )
            resp.raise_for_status()
            return {"sent": True, "to": to, "id": resp.json().get("id")}
    except Exception as exc:
        print(f"[emails] error enviando invitación a {to}: {exc!r}")
        return {"error": str(exc), "to": to}
