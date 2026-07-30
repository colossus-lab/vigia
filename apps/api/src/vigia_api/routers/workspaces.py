"""Gestión del workspace del usuario (JWT requerido)."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select

from vigia_api.core.db import get_sessionmaker
from vigia_api.core.security import (
    WorkspaceContext,
    current_workspace,
    require_active_plan,
    require_escritura,
)
from vigia_api.services.audit import (
    ACTION_INVITE_CREATED,
    ACTION_MEMBER_LEFT,
    ACTION_MEMBER_REMOVED,
    ACTION_ONBOARDED,
    write_audit_event,
)
from vigia_shared.constants import ROL_ADMIN, ROL_OWNER, ROL_VIEWER
from vigia_shared.models import AppUser, Workspace, WorkspaceInvitation, WorkspaceMember

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

INVITE_TTL_DAYS = 14


class MemberOut(BaseModel):
    user_id: int
    email: str
    name: str | None
    role: str
    accepted: bool


class WorkspaceMe(BaseModel):
    id: int
    slug: str
    name: str
    plan: str
    trial_ends_at: datetime | None = None
    role: str
    seat_limit: int
    seats_used: int
    onboarded: bool
    sectores_interes: list[str] | None


class OnboardingBody(BaseModel):
    name: str | None = None
    sectores_interes: list[str] = []


class InviteBody(BaseModel):
    email: EmailStr
    role: str = "viewer"


class InviteOut(BaseModel):
    email: str
    role: str
    token: str
    expires_at: datetime
    accepted: bool
    email_sent: bool = False  # solo significativo en la respuesta del POST


@router.get("/me", response_model=WorkspaceMe)
async def me(ctx: Annotated[WorkspaceContext, Depends(current_workspace)]) -> WorkspaceMe:
    # Exento del check de trial: el cliente necesita poder leer su propio estado
    # (plan, trial_ends_at) incluso con el trial vencido.
    Session = get_sessionmaker()
    async with Session() as session:
        ws = await session.get(Workspace, ctx.workspace_id)
        if ws is None:
            raise HTTPException(404, "workspace_not_found")
        seats = await session.scalar(
            select(func.count()).select_from(WorkspaceMember).where(WorkspaceMember.workspace_id == ws.id)
        )
    return WorkspaceMe(
        id=ws.id, slug=ws.slug, name=ws.name, plan=ws.plan, trial_ends_at=ctx.trial_ends_at,
        role=ctx.role, seat_limit=ws.seat_limit, seats_used=int(seats or 0),
        onboarded=ws.onboarded_at is not None, sectores_interes=ws.sectores_interes,
    )


@router.post("/me/onboarding", response_model=WorkspaceMe)
async def onboarding(
    body: OnboardingBody,
    request: Request,
    ctx: Annotated[WorkspaceContext, Depends(require_escritura)],
) -> WorkspaceMe:
    Session = get_sessionmaker()
    async with Session() as session:
        ws = await session.get(Workspace, ctx.workspace_id)
        if ws is None:
            raise HTTPException(404, "workspace_not_found")
        if body.name:
            ws.name = body.name[:255]
        ws.sectores_interes = body.sectores_interes
        ws.onboarded_at = datetime.now(timezone.utc)
        await write_audit_event(
            session, action=ACTION_ONBOARDED, workspace_id=ws.id, user_id=ctx.user_id,
            params={"sectores": body.sectores_interes}, request=request,
        )
        await session.commit()
        seats = await session.scalar(
            select(func.count()).select_from(WorkspaceMember).where(WorkspaceMember.workspace_id == ws.id)
        )
    return WorkspaceMe(
        id=ws.id, slug=ws.slug, name=ws.name, plan=ws.plan, trial_ends_at=ctx.trial_ends_at,
        role=ctx.role, seat_limit=ws.seat_limit, seats_used=int(seats or 0),
        onboarded=True, sectores_interes=ws.sectores_interes,
    )


@router.get("/me/members", response_model=list[MemberOut])
async def members(ctx: Annotated[WorkspaceContext, Depends(require_active_plan)]) -> list[MemberOut]:
    Session = get_sessionmaker()
    async with Session() as session:
        rows = (
            await session.execute(
                select(WorkspaceMember, AppUser)
                .join(AppUser, AppUser.id == WorkspaceMember.user_id)
                .where(WorkspaceMember.workspace_id == ctx.workspace_id)
                .order_by(WorkspaceMember.invited_at.asc())
            )
        ).all()
    return [
        MemberOut(user_id=u.id, email=u.email, name=u.name, role=m.role, accepted=m.accepted_at is not None)
        for m, u in rows
    ]


@router.post("/me/invitations", response_model=InviteOut)
async def create_invitation(
    body: InviteBody,
    request: Request,
    ctx: Annotated[WorkspaceContext, Depends(require_escritura)],
) -> InviteOut:
    if body.role not in (ROL_ADMIN, ROL_VIEWER):
        raise HTTPException(422, "invalid_role")
    # Solo el owner reparte poder: un admin que puede nombrar admins escala sin
    # techo (invita a un cómplice, que invita a otro…). El admin invita viewers.
    if body.role == ROL_ADMIN and ctx.role != ROL_OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "requires_owner_to_invite_admin")

    Session = get_sessionmaker()
    async with Session() as session:
        # Cuenta miembros + invitaciones pendientes. Contando solo miembros, un
        # workspace de 1 persona con seat_limit=5 podía emitir invitaciones
        # ILIMITADAS a direcciones arbitrarias, y cada una manda un mail firmado
        # con el DKIM de openarg.org. El cupo ahora acota el abuso por diseño.
        seats = await session.scalar(
            select(func.count()).select_from(WorkspaceMember).where(WorkspaceMember.workspace_id == ctx.workspace_id)
        )
        pendientes = await session.scalar(
            select(func.count())
            .select_from(WorkspaceInvitation)
            .where(
                WorkspaceInvitation.workspace_id == ctx.workspace_id,
                WorkspaceInvitation.accepted_at.is_(None),
                WorkspaceInvitation.expires_at > datetime.now(timezone.utc),
            )
        )
        ws = await session.get(Workspace, ctx.workspace_id)
        if int(seats or 0) + int(pendientes or 0) >= ws.seat_limit:
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "seat_limit_reached")

        token = secrets.token_urlsafe(24)
        expires = datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)
        inv = WorkspaceInvitation(
            workspace_id=ctx.workspace_id, email=body.email, role=body.role,
            token=token, expires_at=expires,
        )
        session.add(inv)
        await write_audit_event(
            session, action=ACTION_INVITE_CREATED, workspace_id=ctx.workspace_id, user_id=ctx.user_id,
            resource=body.email, params={"role": body.role}, request=request,
        )
        ws_name = ws.name
        inviter = await session.scalar(
            select(AppUser.name).where(AppUser.id == ctx.user_id)
        )
        await session.commit()

    # Email de invitación best-effort (no-op sin RESEND_API_KEY; el link
    # compartible por WhatsApp/copia es el camino principal).
    from vigia_api.services.emails import send_invitation_email

    sent = await send_invitation_email(
        to=body.email, workspace_name=ws_name, role=body.role, token=token, invited_by=inviter
    )
    return InviteOut(
        email=body.email, role=body.role, token=token, expires_at=expires,
        accepted=False, email_sent=bool(sent.get("sent")),
    )


@router.get("/me/invitations", response_model=list[InviteOut])
async def list_invitations(ctx: Annotated[WorkspaceContext, Depends(require_active_plan)]) -> list[InviteOut]:
    Session = get_sessionmaker()
    async with Session() as session:
        rows = (
            await session.execute(
                select(WorkspaceInvitation)
                .where(WorkspaceInvitation.workspace_id == ctx.workspace_id)
                .order_by(WorkspaceInvitation.created_at.desc())
            )
        ).scalars().all()
    return [
        InviteOut(email=i.email, role=i.role, token=i.token, expires_at=i.expires_at, accepted=i.accepted_at is not None)
        for i in rows
    ]


@router.delete("/me/members/{user_id}", status_code=204)
async def remove_member(
    user_id: int,
    request: Request,
    ctx: Annotated[WorkspaceContext, Depends(require_escritura)],
) -> None:
    if user_id == ctx.user_id:
        raise HTTPException(422, "use_leave_endpoint")
    Session = get_sessionmaker()
    async with Session() as session:
        m = await session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ctx.workspace_id, WorkspaceMember.user_id == user_id
            )
        )
        if m is None:
            raise HTTPException(404, "member_not_found")
        # Un admin no puede echar al dueño: si pudiera, dejaría el workspace sin
        # owner y con el admin como única autoridad. Owner a owner sí se permite
        # (los co-owners se auto-regulan), y `use_leave_endpoint` ya cubre el
        # caso de irse uno mismo.
        if m.role == ROL_OWNER and ctx.role != ROL_OWNER:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "requires_owner_to_remove_owner")
        await session.delete(m)
        await write_audit_event(
            session, action=ACTION_MEMBER_REMOVED, workspace_id=ctx.workspace_id, user_id=ctx.user_id,
            resource=f"user:{user_id}", request=request,
        )
        await session.commit()


@router.post("/me/leave", status_code=204)
async def leave(
    request: Request,
    ctx: Annotated[WorkspaceContext, Depends(require_active_plan)],
) -> None:
    Session = get_sessionmaker()
    async with Session() as session:
        m = await session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ctx.workspace_id, WorkspaceMember.user_id == ctx.user_id
            )
        )
        if m is None:
            raise HTTPException(404, "member_not_found")
        await session.delete(m)
        await write_audit_event(
            session, action=ACTION_MEMBER_LEFT, workspace_id=ctx.workspace_id, user_id=ctx.user_id,
            request=request,
        )
        await session.commit()
