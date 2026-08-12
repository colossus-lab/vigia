"""Gestión de API keys del workspace (sesión requerida).

Ojo con la asimetría: estos endpoints se autentican con la **sesión** (el JWT
que emite el web), no con una key. Una key no puede emitir otra key — si una se
filtra, el daño queda acotado a leer `/v1`, y no incluye fabricarse credenciales
nuevas ni revocar las existentes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update

from vigia_api.core.apikeys import generar
from vigia_api.core.db import get_sessionmaker
from vigia_api.core.ratelimit import limitar_por_workspace
from vigia_api.core.security import (
    WorkspaceContext,
    require_active_plan,
    require_escritura,
)
from vigia_api.core.settings import Settings, get_settings
from vigia_api.services.audit import (
    ACTION_APIKEY_CREATED,
    ACTION_APIKEY_REVOKED,
    write_audit_event,
)
from vigia_shared.models import ApiKey

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

# Crear una key es barato para el server pero genera un secreto: acotamos el
# ritmo para que un token de sesión robado no pueda sembrar credenciales de
# larga vida a toda velocidad.
#
# Tiene que quedar POR ENCIMA de `apikey_max_por_workspace`: si fueran iguales,
# el que llega al techo de keys comería un 429 genérico en vez del 409 que le
# explica qué pasa, y el chequeo de abajo sería inalcanzable.
_limite_alta = limitar_por_workspace("apikeys_create", limite=30, ventana=3600)


class ApiKeyOut(BaseModel):
    """La key tal como se la puede ver después de creada: sin el secreto."""

    id: int
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None

    @property
    def activa(self) -> bool:
        return self.revoked_at is None


class ApiKeyCreated(ApiKeyOut):
    """Respuesta del alta. **Única vez** que el secreto viaja."""

    secret: str = Field(
        description="Guardalo ahora: no se puede volver a ver. Si se pierde, revocá y creá otra."
    )


class ApiKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120, description="Para qué es (ej: 'ETL interno').")

    @field_validator("name")
    @classmethod
    def _limpiar(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("el nombre no puede ser solo espacios")
        return v


def _require_real_workspace(ctx: WorkspaceContext) -> None:
    """En modo demo el workspace es ficticio (id 0) y no puede tener credenciales."""
    if ctx.workspace_id == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="auth_required_for_api_keys"
        )


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(
    ctx: Annotated[WorkspaceContext, Depends(require_active_plan)],
) -> list[ApiKeyOut]:
    """Las keys del workspace, revocadas incluidas (el historial importa)."""
    _require_real_workspace(ctx)
    Session = get_sessionmaker()
    async with Session() as session:
        filas = (
            await session.execute(
                select(ApiKey)
                .where(ApiKey.workspace_id == ctx.workspace_id)
                .order_by(ApiKey.revoked_at.isnot(None), ApiKey.created_at.desc())
            )
        ).scalars().all()
    return [ApiKeyOut.model_validate(f, from_attributes=True) for f in filas]


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: ApiKeyIn,
    request: Request,
    ctx: Annotated[WorkspaceContext, Depends(require_escritura)],
    _limite: Annotated[WorkspaceContext, Depends(_limite_alta)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiKeyCreated:
    """Emite una key nueva. El secreto se devuelve acá y **nunca más**.

    Va con `require_escritura` (owner|admin) y no con `require_active_plan`: una
    key da acceso de lectura a todo el corpus en nombre del workspace, así que
    un `viewer` no debería poder acuñar una.
    """
    _require_real_workspace(ctx)
    secreto, prefijo, token_hash = generar()

    Session = get_sessionmaker()
    async with Session() as session:
        vivas = (
            await session.execute(
                select(func.count())
                .select_from(ApiKey)
                .where(ApiKey.workspace_id == ctx.workspace_id, ApiKey.revoked_at.is_(None))
            )
        ).scalar_one()
        if vivas >= settings.apikey_max_por_workspace:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"limite_de_keys_alcanzado: {settings.apikey_max_por_workspace}",
            )

        key = ApiKey(
            workspace_id=ctx.workspace_id,
            created_by_user_id=ctx.user_id or None,
            name=body.name,
            prefix=prefijo,
            token_hash=token_hash,
        )
        session.add(key)
        await session.flush()
        await write_audit_event(
            session,
            action=ACTION_APIKEY_CREATED,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user_id or None,
            resource=f"api_key:{key.id}",
            params={"name": key.name, "prefix": key.prefix},
            request=request,
        )
        await session.commit()
        await session.refresh(key)

    salida = ApiKeyCreated.model_validate(
        {**ApiKeyOut.model_validate(key, from_attributes=True).model_dump(), "secret": secreto}
    )
    return salida


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    api_key_id: int,
    request: Request,
    ctx: Annotated[WorkspaceContext, Depends(require_escritura)],
) -> None:
    """Revoca la key. La fila queda: es lo que explica el audit log viejo.

    Idempotente — revocar dos veces no es un error, y así el que automatiza no
    tiene que distinguir "ya estaba" de "no existe".
    """
    _require_real_workspace(ctx)
    Session = get_sessionmaker()
    async with Session() as session:
        # El filtro por workspace va en el UPDATE, no en un chequeo aparte: es lo
        # que impide revocar la key de otro tenant conociendo solo su id.
        resultado = await session.execute(
            update(ApiKey)
            .where(
                ApiKey.id == api_key_id,
                ApiKey.workspace_id == ctx.workspace_id,
                ApiKey.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )
        if resultado.rowcount == 0:
            existe = (
                await session.execute(
                    select(ApiKey.id).where(
                        ApiKey.id == api_key_id, ApiKey.workspace_id == ctx.workspace_id
                    )
                )
            ).first()
            if existe is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="api_key_no_encontrada"
                )
            return  # ya estaba revocada
        await write_audit_event(
            session,
            action=ACTION_APIKEY_REVOKED,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user_id or None,
            resource=f"api_key:{api_key_id}",
            request=request,
        )
        await session.commit()
