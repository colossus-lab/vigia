"""Alertas de monitoreo (JWT requerido). Persistidas por workspace.

El matching norma↔alerta lo hace el worker (`vigia_workers.alerts`); acá sólo
se gestionan las suscripciones y se leen los matches.
"""
from __future__ import annotations

import math
from datetime import date as Date
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select, text, update

from vigia_api.core.db import get_sessionmaker
from vigia_api.core.ratelimit import limitar_por_workspace
from vigia_api.core.security import (
    WorkspaceContext,
    current_workspace,
    require_active_plan,
    require_escritura,
)
from vigia_shared.constants import SECTORES
from vigia_shared.models import Alerta, AlertaMatch, Norma

router = APIRouter(prefix="/alerts", tags=["alerts"])

# `/alerts/preview` corre full-text sobre `norma` (un COUNT + un SELECT con
# ORDER BY) sin cache y sin tope de keywords. Con 10 conexiones en el pool
# (core/db.py) una ráfaga lo satura antes que a la CPU. 30/min por workspace es
# holgado para tipear un criterio y probarlo, y corta el abuso.
_limite_preview = limitar_por_workspace("alerts_preview", limite=30, ventana=60)


def _require_real_workspace(ctx: WorkspaceContext) -> None:
    if ctx.workspace_id == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="auth_required_for_alerts",
        )


def _clean_keywords(keywords: list[str]) -> list[str]:
    """Normaliza la lista de keywords: strip, sin vacías, sin duplicados (preserva orden)."""
    seen: list[str] = []
    for kw in keywords:
        kw = kw.strip()
        if kw and kw not in seen:
            seen.append(kw)
    return seen


def _clean_sectores(sectores: list[str]) -> list[str]:
    """Valida que cada sector exista en el catálogo; descarta duplicados."""
    seen: list[str] = []
    for s in sectores:
        if s not in SECTORES:
            raise HTTPException(422, f"sector_invalido: {s}")
        if s not in seen:
            seen.append(s)
    return seen


def _require_criterio(keywords: list[str], sectores: list[str]) -> None:
    """Una alerta necesita al menos un criterio: keywords O sectores.

    Antes se exigía ≥1 keyword; ahora una alerta por-sector (keywords vacío,
    sectores no vacío) es válida y monitorea todas las normas de esos sectores.
    """
    if not keywords and not sectores:
        raise HTTPException(422, "criterio_vacio")


class AlertaIn(BaseModel):
    keywords: list[str] = []
    sectores: list[str] = []


class AlertaPatch(BaseModel):
    keywords: list[str] | None = None
    sectores: list[str] | None = None
    activa: bool | None = None


class AlertaOut(BaseModel):
    id: int
    keywords: list[str]
    sectores: list[str]
    activa: bool
    matches: int
    last_match_at: datetime | None


class MatchOut(BaseModel):
    norma_id: int
    tipo: str
    numero: str | None
    titulo: str
    fecha_publicacion: Date | None
    matched_at: datetime


class PreviewIn(BaseModel):
    keywords: list[str] = []
    sectores: list[str] = []


class PreviewSample(BaseModel):
    tipo: str
    titulo: str
    fecha_publicacion: Date | None


class PreviewOut(BaseModel):
    count_30d: int
    #: Cuántos créditos consumiría al mes (1 crédito = 1 mail). Ver `_digests_estimados`.
    creditos_estimados_mes: int
    sample: list[PreviewSample]


#: Techo de mails que un workspace puede recibir en un mes.
#:
#: No es 30×24 aunque el matcher corra cada hora: las normas llegan en ráfagas
#: (una edición del BORA entera de golpe), así que lo que manda es cuántas
#: ventanas de ingesta traen algo. Calibrado contra 30 días de producción, donde
#: el workspace más pesado —con 14 alertas— recibió 60.
_TECHO_MAILS_MES = 60


def _digests_estimados(count_30d: int) -> int:
    """De "cuántas normas matchean" a "cuántos mails vas a recibir".

    No son lo mismo y por mucho: 20 normas que caen juntas en una corrida viajan
    en un solo mail. El modelo es el de ventanas ocupadas —cuántas de las ~60
    ráfagas del mes traen al menos una coincidencia— que se comporta bien en las
    dos puntas: con pocas normas da ~1 mail por norma, y con muchas satura en el
    techo en vez de crecer para siempre.

    Contrastado con producción: 20 normas/mes → 17 (la mediana real es 18);
    200 → 58 (el máximo real es 60).

    Es por-alerta y de arriba: varias alertas que coinciden en la misma corrida
    viajan en el mismo mail y se cobran una sola vez.
    """
    if count_30d <= 0:
        return 0
    return round(_TECHO_MAILS_MES * (1 - math.exp(-count_30d / _TECHO_MAILS_MES)))


@router.get("", response_model=list[AlertaOut])
async def list_alertas(ctx: Annotated[WorkspaceContext, Depends(require_active_plan)]) -> list[AlertaOut]:
    _require_real_workspace(ctx)
    Session = get_sessionmaker()
    async with Session() as session:
        rows = (
            await session.execute(
                select(Alerta, func.count(AlertaMatch.id))
                .outerjoin(AlertaMatch, AlertaMatch.alerta_id == Alerta.id)
                .where(Alerta.workspace_id == ctx.workspace_id)
                .group_by(Alerta.id)
                .order_by(Alerta.created_at.desc())
            )
        ).all()
    return [
        AlertaOut(
            id=a.id, keywords=a.keywords, sectores=a.sectores, activa=a.activa,
            matches=int(c or 0), last_match_at=a.last_match_at,
        )
        for a, c in rows
    ]


@router.post("", response_model=AlertaOut, status_code=201)
async def create_alerta(
    body: AlertaIn,
    ctx: Annotated[WorkspaceContext, Depends(require_escritura)],
) -> AlertaOut:
    _require_real_workspace(ctx)
    keywords = _clean_keywords(body.keywords)
    sectores = _clean_sectores(body.sectores)
    _require_criterio(keywords, sectores)
    Session = get_sessionmaker()
    async with Session() as session:
        a = Alerta(
            workspace_id=ctx.workspace_id,
            user_id=ctx.user_id or None,
            keywords=keywords,
            sectores=sectores,
            activa=True,
        )
        session.add(a)
        await session.commit()
        await session.refresh(a)
    return AlertaOut(
        id=a.id, keywords=a.keywords, sectores=a.sectores, activa=a.activa,
        matches=0, last_match_at=None,
    )


@router.post("/preview", response_model=PreviewOut)
async def preview_alerta(
    body: PreviewIn,
    ctx: Annotated[WorkspaceContext, Depends(_limite_preview)],
) -> PreviewOut:
    """Estima cuántas normas matchearía un criterio (keywords + sectores).

    Cuenta sobre los últimos 30 días de `norma` como proxy del volumen futuro
    ("~N/mes"), usando la MISMA lógica que el matcher (OR de `plainto_tsquery`
    español entre keywords, `sector = ANY` entre sectores) pero sin el filtro de
    `anchor` ni el `NOT EXISTS`. Solo lectura: no exige plan activo (el gating de
    creación de alertas vive en los otros endpoints)."""
    keywords = _clean_keywords(body.keywords)
    sectores = _clean_sectores(body.sectores)
    _require_criterio(keywords, sectores)

    params: dict = {}
    where = ["n.fecha_publicacion >= (now() - interval '30 days')"]
    if keywords:
        ts_parts = []
        for i, kw in enumerate(keywords):
            ts_parts.append(f"plainto_tsquery('spanish', :kw{i})")
            params[f"kw{i}"] = kw
        where.append(f"n.search_vector @@ ({' || '.join(ts_parts)})")
    if sectores:
        where.append("n.sector = ANY(:sectores)")
        params["sectores"] = sectores
    where_sql = " AND ".join(where)

    Session = get_sessionmaker()
    async with Session() as session:
        count = await session.scalar(
            text(f"SELECT count(*) FROM norma n WHERE {where_sql}"), params
        )
        rows = (
            await session.execute(
                text(
                    f"SELECT tipo, titulo, fecha_publicacion FROM norma n WHERE {where_sql} "
                    "ORDER BY fecha_publicacion DESC NULLS LAST LIMIT 3"
                ),
                params,
            )
        ).all()
    return PreviewOut(
        count_30d=int(count or 0),
        creditos_estimados_mes=_digests_estimados(int(count or 0)),
        sample=[
            PreviewSample(tipo=r.tipo, titulo=r.titulo, fecha_publicacion=r.fecha_publicacion)
            for r in rows
        ],
    )


@router.patch("/{alerta_id}", response_model=AlertaOut)
async def update_alerta(
    alerta_id: int,
    body: AlertaPatch,
    ctx: Annotated[WorkspaceContext, Depends(require_escritura)],
) -> AlertaOut:
    """Edita una alerta. Solo aplica los campos provistos.

    Cambiar el criterio (`keywords`/`sectores`) re-ancla la alerta a now() y
    descarta los matches existentes (eran de otro criterio): la alerta arranca
    limpia y solo notifica normas nuevas desde la edición. Togglear `activa` no
    toca el ancla ni los matches.
    """
    _require_real_workspace(ctx)
    Session = get_sessionmaker()
    async with Session() as session:
        a = await session.scalar(
            select(Alerta).where(Alerta.id == alerta_id, Alerta.workspace_id == ctx.workspace_id)
        )
        if a is None:
            raise HTTPException(404, "alerta_not_found")

        criterio_cambio = False
        if body.keywords is not None:
            a.keywords = _clean_keywords(body.keywords)
            criterio_cambio = True
        if body.sectores is not None:
            a.sectores = _clean_sectores(body.sectores)
            criterio_cambio = True
        if body.activa is not None:
            a.activa = body.activa

        if criterio_cambio:
            _require_criterio(a.keywords, a.sectores)
            a.anchor_at = func.now()
            a.last_match_at = None
            await session.execute(
                delete(AlertaMatch).where(AlertaMatch.alerta_id == a.id)
            )
        await session.commit()
        await session.refresh(a)
        count = await session.scalar(
            select(func.count()).select_from(AlertaMatch).where(AlertaMatch.alerta_id == a.id)
        )
    return AlertaOut(
        id=a.id, keywords=a.keywords, sectores=a.sectores, activa=a.activa,
        matches=int(count or 0), last_match_at=a.last_match_at,
    )


@router.delete("/{alerta_id}", status_code=204)
async def delete_alerta(
    alerta_id: int,
    ctx: Annotated[WorkspaceContext, Depends(require_escritura)],
) -> None:
    _require_real_workspace(ctx)
    Session = get_sessionmaker()
    async with Session() as session:
        res = await session.execute(
            delete(Alerta).where(Alerta.id == alerta_id, Alerta.workspace_id == ctx.workspace_id)
        )
        if res.rowcount == 0:
            raise HTTPException(404, "alerta_not_found")
        await session.commit()


@router.get("/{alerta_id}/matches", response_model=list[MatchOut])
async def alerta_matches(
    alerta_id: int,
    ctx: Annotated[WorkspaceContext, Depends(require_active_plan)],
) -> list[MatchOut]:
    _require_real_workspace(ctx)
    Session = get_sessionmaker()
    async with Session() as session:
        owns = await session.scalar(
            select(Alerta.id).where(Alerta.id == alerta_id, Alerta.workspace_id == ctx.workspace_id)
        )
        if owns is None:
            raise HTTPException(404, "alerta_not_found")
        rows = (
            await session.execute(
                select(AlertaMatch, Norma)
                .join(Norma, Norma.id == AlertaMatch.norma_id)
                .where(AlertaMatch.alerta_id == alerta_id)
                .order_by(AlertaMatch.matched_at.desc())
                .limit(50)
            )
        ).all()
    return [
        MatchOut(
            norma_id=n.id, tipo=n.tipo, numero=n.numero, titulo=n.titulo,
            fecha_publicacion=n.fecha_publicacion, matched_at=m.matched_at,
        )
        for m, n in rows
    ]
