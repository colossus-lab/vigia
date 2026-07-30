"""Derechos del titular de los datos (Ley 25.326): acceso/portabilidad y supresión.

`GET /account/export` — descarga todos los datos personales del usuario.
`DELETE /account` — supresión total de la cuenta y sus datos.

Ambos están protegidos por el JWT (`current_workspace`) pero NO por
`require_active_plan`: el ejercicio de derechos no puede quedar detrás del trial
vencido.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select

from vigia_api.core.db import get_sessionmaker
from vigia_api.core.ratelimit import limitar_por_usuario
from vigia_api.core.security import WorkspaceContext, current_workspace
from vigia_shared.models import (
    Alerta,
    AppUser,
    AuditLog,
    Workspace,
    WorkspaceInvitation,
    WorkspaceMember,
)

router = APIRouter(prefix="/account", tags=["account"])

# Borrar la cuenta dispara cascadas caras (workspaces, alertas, audit log) y es
# irreversible. Nadie lo hace tres veces por hora de buena fe.
_limite_borrado = limitar_por_usuario("account_delete", limite=3, ventana=60 * 60)


@router.get("/export")
async def export_account(
    ctx: Annotated[WorkspaceContext, Depends(current_workspace)],
) -> JSONResponse:
    """Derecho de acceso/portabilidad: todos los datos personales del usuario en JSON."""
    Session = get_sessionmaker()
    async with Session() as session:
        user = await session.get(AppUser, ctx.user_id)
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")

        memberships = (
            await session.execute(
                select(WorkspaceMember, Workspace)
                .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
                .where(WorkspaceMember.user_id == user.id)
                .order_by(WorkspaceMember.invited_at.asc())
            )
        ).all()

        alertas = (
            await session.execute(
                select(Alerta).where(Alerta.user_id == user.id).order_by(Alerta.created_at.asc())
            )
        ).scalars().all()

        audit = (
            await session.execute(
                select(AuditLog)
                .where(AuditLog.user_id == user.id)
                .order_by(AuditLog.created_at.asc())
            )
        ).scalars().all()

        invitations = (
            await session.execute(
                select(WorkspaceInvitation)
                .where(
                    or_(
                        WorkspaceInvitation.accepted_by_user_id == user.id,
                        WorkspaceInvitation.email == user.email,
                    )
                )
                .order_by(WorkspaceInvitation.created_at.asc())
            )
        ).scalars().all()

    payload = {
        "exportado_segun": "Ley 25.326 — derecho de acceso (art. 14)",
        "cuenta": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "image_url": user.image_url,
            "provider": user.provider,
            "provider_id": user.provider_id,
            "created_at": user.created_at,
            "last_seen_at": user.last_seen_at,
        },
        "workspaces": [
            {
                "id": ws.id,
                "slug": ws.slug,
                "name": ws.name,
                "role": m.role,
                "invited_at": m.invited_at,
                "accepted_at": m.accepted_at,
            }
            for m, ws in memberships
        ],
        "alertas": [
            {
                "id": a.id,
                "workspace_id": a.workspace_id,
                "keywords": a.keywords,
                "sectores": a.sectores,
                "activa": a.activa,
                "created_at": a.created_at,
            }
            for a in alertas
        ],
        "registro_de_actividad": [
            {
                "action": e.action,
                "resource": e.resource,
                "params": e.params,
                "ip": e.ip,
                "user_agent": e.user_agent,
                "created_at": e.created_at,
            }
            for e in audit
        ],
        "invitaciones": [
            {
                "workspace_id": i.workspace_id,
                "email": i.email,
                "role": i.role,
                "accepted_at": i.accepted_at,
                "created_at": i.created_at,
            }
            for i in invitations
        ],
    }

    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={"Content-Disposition": 'attachment; filename="vigia-mis-datos.json"'},
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    ctx: Annotated[WorkspaceContext, Depends(_limite_borrado)],
) -> None:
    """Derecho de supresión: borra la cuenta y todos sus datos.

    - Workspaces donde el usuario es el único miembro: se borran enteros (la FK
      `ondelete=CASCADE` arrastra alertas, invitaciones y audit_log).
    - Workspaces compartidos donde es owner: se promueve al miembro más antiguo
      a owner para no dejar el tenant sin dueño.
    - Finalmente se borra `app_user`; las FKs `user_id` en alerta/audit/invitation
      quedan en NULL (anonimizadas) en los workspaces ajenos.
    """
    Session = get_sessionmaker()
    async with Session() as session:
        user = await session.get(AppUser, ctx.user_id)
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")

        memberships = (
            await session.execute(
                select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
            )
        ).scalars().all()

        for m in memberships:
            members_count = await session.scalar(
                select(func.count())
                .select_from(WorkspaceMember)
                .where(WorkspaceMember.workspace_id == m.workspace_id)
            )
            if int(members_count or 0) <= 1:
                # Único miembro → borrar el workspace completo (cascada).
                ws = await session.get(Workspace, m.workspace_id)
                if ws is not None:
                    await session.delete(ws)
                continue

            # Workspace compartido: si el que se va es el único owner, promover
            # al miembro más antiguo restante para no dejarlo huérfano.
            if m.role == "owner":
                other_owner = await session.scalar(
                    select(func.count())
                    .select_from(WorkspaceMember)
                    .where(
                        WorkspaceMember.workspace_id == m.workspace_id,
                        WorkspaceMember.user_id != user.id,
                        WorkspaceMember.role == "owner",
                    )
                )
                if int(other_owner or 0) == 0:
                    heir = await session.scalar(
                        select(WorkspaceMember)
                        .where(
                            WorkspaceMember.workspace_id == m.workspace_id,
                            WorkspaceMember.user_id != user.id,
                        )
                        .order_by(WorkspaceMember.invited_at.asc())
                        .limit(1)
                    )
                    if heir is not None:
                        heir.role = "owner"

        # Borra la cuenta. Las membresías restantes (workspaces compartidos) caen
        # por CASCADE; alerta/audit/invitation quedan con user_id NULL.
        await session.delete(user)
        await session.commit()
