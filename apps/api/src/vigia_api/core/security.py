"""JWT signing/verification + dependencies FastAPI para multi-tenant.

- El web (NextAuth) firma un JWT con `{sub=user_id, ws=workspace_id, role}`
  tras Google OAuth + workspace upsert, usando el mismo `AUTH_SECRET` que la API.
- Cada request a endpoints protegidos pasa `Authorization: Bearer <jwt>`.
- `auth_enabled=False` deja la API en modo demo (sin gating).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status

from vigia_api.core.db import get_sessionmaker
from vigia_api.core.settings import Settings, get_settings
from vigia_shared.constants import ROLES_ESCRITURA
from vigia_shared.models import Workspace, WorkspaceMember
from sqlalchemy import select


@dataclass(frozen=True)
class WorkspaceContext:
    user_id: int
    workspace_id: int
    role: str
    plan: str
    trial_ends_at: datetime | None = None

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"

    @property
    def trial_expired(self) -> bool:
        """True solo para plan free con trial vencido. Cualquier otro plan = membresía."""
        if self.plan != "free" or self.trial_ends_at is None:
            return False
        return datetime.now(timezone.utc) > self.trial_ends_at


def sign_jwt(*, user_id: int, workspace_id: int, role: str, settings: Settings | None = None) -> str:
    s = settings or get_settings()
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "ws": workspace_id,
        "role": role,
        "iat": now,
        "exp": now + s.auth_jwt_ttl_seconds,
    }
    return jwt.encode(payload, s.auth_secret, algorithm=s.auth_jwt_alg)


def verify_jwt(token: str, settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    try:
        return jwt.decode(token, s.auth_secret, algorithms=[s.auth_jwt_alg])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid_token: {exc.__class__.__name__}",
        ) from exc


def trial_ends_at_for(created_at: datetime | None, settings: Settings) -> datetime | None:
    if created_at is None:
        return None
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at + timedelta(days=settings.trial_days)


async def _load_workspace_context(
    user_id: int, workspace_id: int, settings: Settings
) -> WorkspaceContext:
    Session = get_sessionmaker()
    async with Session() as session:
        row = (
            await session.execute(
                select(Workspace, WorkspaceMember)
                .join(
                    WorkspaceMember,
                    (WorkspaceMember.workspace_id == Workspace.id)
                    & (WorkspaceMember.user_id == user_id),
                )
                .where(Workspace.id == workspace_id)
            )
        ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not_a_member_of_workspace")
    ws, member = row
    return WorkspaceContext(
        user_id=user_id,
        workspace_id=ws.id,
        role=member.role,
        plan=ws.plan,
        trial_ends_at=trial_ends_at_for(ws.created_at, settings),
    )


async def current_workspace(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> WorkspaceContext:
    """Dependency: 401 sin Bearer, 403 si no es miembro. En modo demo devuelve un contexto ficticio."""
    if not settings.auth_enabled:
        return WorkspaceContext(user_id=0, workspace_id=0, role="owner", plan="free")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_bearer_token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    payload = verify_jwt(token, settings=settings)
    try:
        user_id = int(payload["sub"])
        workspace_id = int(payload["ws"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="malformed_token_claims") from exc
    return await _load_workspace_context(user_id, workspace_id, settings)


async def require_active_plan(
    ctx: Annotated[WorkspaceContext, Depends(current_workspace)],
) -> WorkspaceContext:
    """Dependency: exige sesión autenticada + membresía del workspace.

    La plataforma es gratuita: ya no se gatea por free trial (antes devolvía 402
    trial_expired a los 30 días). Se mantiene como punto único de gating por si
    vuelve a hacer falta; hoy es equivalente a `current_workspace`.

    OJO: NO valida rol. Para endpoints que escriben, usar `require_escritura`.
    """
    return ctx


def require_role(*roles: str):
    """Dependency factory: 403 si el rol del contexto no está en `roles`.

    El rol sale de `WorkspaceContext`, que lo relee de la base en
    `_load_workspace_context` — NO se confía del claim del JWT, así que un token
    manipulado no escala privilegios.
    """
    permitidos = tuple(roles)
    detalle = "requires_" + "_or_".join(permitidos)

    async def _dep(
        ctx: Annotated[WorkspaceContext, Depends(current_workspace)],
    ) -> WorkspaceContext:
        if ctx.role not in permitidos:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detalle)
        return ctx

    return _dep


# Escritura sobre recursos del workspace: alertas y onboarding. El `viewer` lee
# todo pero no modifica nada. El detalle del 403 queda `requires_owner_or_admin`,
# igual que el que ya devolvían los chequeos inline de workspaces.py.
require_escritura = require_role(*ROLES_ESCRITURA)
