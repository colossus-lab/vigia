"""Auth server-to-server entre web (NextAuth) y API.

`POST /auth/sync` es la única forma en que el web crea/recupera el contexto de
un usuario tras Google OAuth. Se llama con `AUTH_SECRET` como bearer interno —
nunca expone tokens de Google al cliente.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vigia_api.core.db import get_sessionmaker
from vigia_api.core.ratelimit import client_ip, consultar, rechazar, registrar
from vigia_api.core.security import sign_jwt, trial_ends_at_for
from vigia_api.core.settings import Settings, get_settings
from vigia_api.services.audit import ACTION_LOGIN, write_audit_event
from vigia_shared.models import AppUser, Workspace, WorkspaceMember

router = APIRouter(prefix="/auth", tags=["auth"])

# Fuerza bruta del AUTH_SECRET: 10 fallos por IP en 15 minutos. El secreto de
# producción tiene 64 caracteres, así que esto no lo hace inviable — ya lo era —
# pero corta el ruido y deja rastro antes de que alguien lo intente en serio.
_MAX_FALLOS = 10
_VENTANA_FALLOS = 15 * 60


class SyncRequest(BaseModel):
    email: EmailStr
    name: str | None = None
    image_url: str | None = None
    provider: str = "google"
    provider_id: str | None = None


class SyncResponse(BaseModel):
    user_id: int
    workspace_id: int
    workspace_slug: str
    workspace_name: str
    role: str
    plan: str
    trial_ends_at: datetime | None = None
    onboarded: bool
    jwt: str


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (s or "workspace")[:48]


async def _unique_slug(session: AsyncSession, base: str) -> str:
    slug = base
    for i in range(6):
        exists = await session.scalar(select(Workspace.id).where(Workspace.slug == slug))
        if exists is None:
            return slug
        slug = f"{base}-{secrets.token_hex(2)}"
    return f"{base}-{secrets.token_hex(4)}"


def _require_internal_secret(
    authorization: str | None, settings: Settings, request: Request | None = None
) -> None:
    """Valida el secreto del canal interno web→API, con freno a la fuerza bruta.

    Se limitan los FALLOS, no los intentos, y eso es deliberado: `/auth/sync` lo
    llama el server de Next en cada login, así que TODO el tráfico legítimo llega
    desde el puñado de IPs de Vercel. Un límite por intentos las estrangularía a
    todas y rompería el login en cualquier pico. Limitando fallos, quien acierta
    el secreto nunca se frena y quien lo adivina a ciegas se queda afuera.
    """
    ip = client_ip(request) or "desconocida"
    clave = f"auth_sync_fallos:ip:{ip}"
    if settings.ratelimit_enabled:
        espera = consultar(clave, _MAX_FALLOS, _VENTANA_FALLOS)
        if espera is not None:
            raise rechazar(espera, "too_many_failed_attempts")

    def _fallo(detalle: str, code: int) -> HTTPException:
        if settings.ratelimit_enabled:
            registrar(clave, _VENTANA_FALLOS)
        return HTTPException(status_code=code, detail=detalle)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise _fallo("missing_internal_token", status.HTTP_401_UNAUTHORIZED)
    token = authorization.split(" ", 1)[1].strip()
    # Rechazo explícito del par vacío: `compare_digest("", "")` es True, así que
    # un `Authorization: Bearer ` pelado contra un secreto vacío pasaría la
    # validación y /auth/sync mintea un JWT para CUALQUIER email. El validador de
    # arranque ya impide el secreto vacío con auth prendida; esto es el segundo
    # cerrojo, para que la condición no dependa de una sola comprobación.
    if not token or not settings.auth_secret:
        raise _fallo("invalid_internal_token", status.HTTP_403_FORBIDDEN)
    if not secrets.compare_digest(token, settings.auth_secret):
        raise _fallo("invalid_internal_token", status.HTTP_403_FORBIDDEN)


@router.post("/sync", response_model=SyncResponse)
async def sync_user(
    body: SyncRequest,
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> SyncResponse:
    _require_internal_secret(authorization, settings, request)

    Session = get_sessionmaker()
    async with Session() as session:
        now = datetime.now(timezone.utc)

        user = await session.scalar(select(AppUser).where(AppUser.email == body.email))
        if user is None:
            user = AppUser(
                email=body.email, name=body.name, image_url=body.image_url,
                provider=body.provider, provider_id=body.provider_id, last_seen_at=now,
            )
            session.add(user)
            await session.flush()
        else:
            user.name = body.name or user.name
            user.image_url = body.image_url or user.image_url
            user.provider_id = body.provider_id or user.provider_id
            user.last_seen_at = now

        membership_row = (
            await session.execute(
                select(WorkspaceMember, Workspace)
                .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
                .where(WorkspaceMember.user_id == user.id)
                .order_by(WorkspaceMember.invited_at.asc())
                .limit(1)
            )
        ).first()

        if membership_row is None:
            base = _slugify(body.name or body.email.split("@")[0])
            slug = await _unique_slug(session, base)
            ws_name = (body.name or body.email.split("@")[0]).strip()
            ws = Workspace(slug=slug, name=f"{ws_name}"[:255] or "Workspace", plan="free", seat_limit=5)
            session.add(ws)
            await session.flush()
            member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner", accepted_at=now)
            session.add(member)
            await session.flush()
        else:
            member, ws = membership_row

        await write_audit_event(
            session, action=ACTION_LOGIN, workspace_id=ws.id, user_id=user.id,
            resource=f"workspace:{ws.slug}", params={"provider": body.provider}, request=request,
        )
        await session.commit()

        token = sign_jwt(user_id=user.id, workspace_id=ws.id, role=member.role, settings=settings)
        # Workspace recién creado: created_at lo pone server_default y no está
        # cargado en el objeto → el trial arranca ahora.
        trial_ends = trial_ends_at_for(ws.created_at or now, settings)
        return SyncResponse(
            user_id=user.id, workspace_id=ws.id, workspace_slug=ws.slug, workspace_name=ws.name,
            role=member.role, plan=ws.plan, trial_ends_at=trial_ends,
            onboarded=ws.onboarded_at is not None, jwt=token,
        )
