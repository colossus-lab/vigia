"""SQLAlchemy 2.0 models para Vigía.

Diseño (Fase 1 — datos reales sin auth):
- `source_catalog` describe una fuente externa (InfoLEG, HCDN, Senado, BORA)
  con su última corrida y estado.
- `norma` es el corpus central: cada norma publicada (ley, decreto, DNU,
  resolución, disposición, proyecto). Reemplaza el `NORMAS_FEED` del mock.
- `dnu_tracking` sigue el tratamiento bicameral de cada DNU.

Las tablas multi-tenant (`app_user`, `workspace`, ...) y de alertas se agregan
en las Fases 2 y 3 respectivamente, en migraciones posteriores.

El esquema soporta dejar de pegarle a las fuentes públicas en cada request:
la API lee de Postgres y los workers ingestan en background (upsert idempotente
por `(source_id, external_id)`).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SourceCatalog(Base):
    __tablename__ = "source_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # api | scrape | feed
    base_url: Mapped[str | None] = mapped_column(String(512))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(32))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    normas: Mapped[list[Norma]] = relationship(back_populates="source")


class Norma(Base):
    """Corpus central: una fila por norma publicada / proyecto en trámite.

    El `search_vector` es una columna generada (tsvector spanish) creada en la
    migración con índice GIN, para full-text search sin pegarle a las fuentes.
    """

    __tablename__ = "norma"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_norma_source_external"),
        Index("ix_norma_fecha", "fecha_publicacion"),
        # Calca el ORDER BY del feed (fecha DESC NULLS LAST, id DESC). Sin él,
        # `ix_norma_fecha` no sirve (es ASC y la columna es nullable) y cada
        # request ordena la tabla entera. Ver migración 0008.
        Index("ix_norma_feed", text("fecha_publicacion DESC NULLS LAST, id DESC")),
        Index("ix_norma_tipo_sector", "tipo", "sector"),
        Index("ix_norma_emisor", "emisor"),
        Index("ix_norma_impacto", "impacto"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("source_catalog.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)

    tipo: Mapped[str] = mapped_column(String(32), nullable=False)  # DNU|DECRETO|LEY|RESOLUCION|DISPOSICION|PROYECTO|OTRA
    numero: Mapped[str | None] = mapped_column(String(64))
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    resumen: Mapped[str | None] = mapped_column(Text)            # texto/resumen oficial real
    resumen_ia: Mapped[str | None] = mapped_column(Text)         # Fase 5 (LLM) — nullable hasta entonces

    fecha_publicacion: Mapped[date | None] = mapped_column(Date)
    jurisdiccion: Mapped[str | None] = mapped_column(String(64))
    sector: Mapped[str | None] = mapped_column(String(64))
    emisor: Mapped[str | None] = mapped_column(String(64))  # organismo canónico (ARCA, CNV, …)
    organismo: Mapped[str | None] = mapped_column(String(255))
    estado: Mapped[str | None] = mapped_column(String(128))
    impacto: Mapped[str | None] = mapped_column(String(16))      # alto | medio | bajo
    bora_seccion: Mapped[str | None] = mapped_column(String(64))

    entidades: Mapped[list[str] | None] = mapped_column(JSONB)   # NER (Fase 5); vacío por ahora
    tags: Mapped[list[str] | None] = mapped_column(JSONB)
    url: Mapped[str | None] = mapped_column(String(1024))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Columna generada (ver migración). Solo-lectura desde el ORM.
    search_vector: Mapped[Any | None] = mapped_column(TSVECTOR)

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    source: Mapped[SourceCatalog] = relationship(back_populates="normas")
    dnu_tracking: Mapped["DnuTracking | None"] = relationship(
        back_populates="norma", uselist=False, cascade="all, delete-orphan"
    )


class AvisoSocietario(Base):
    """BORA 2ª sección: constituciones, asambleas, edictos (módulo Radar societario).

    Tabla propia a propósito: ~200-400 avisos/día contaminarían el corpus
    `norma` (feed, stats y alertas FTS). Tiene su propio tsvector (migración
    0005) con peso A en razón social — "vigilar una empresa" es la feature.
    """

    __tablename__ = "aviso_societario"
    __table_args__ = (
        Index("ix_aviso_fecha", "fecha"),
        Index("ix_aviso_rubro", "rubro"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    aviso_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    razon_social: Mapped[str | None] = mapped_column(String(512))
    rubro: Mapped[str | None] = mapped_column(String(255))
    texto: Mapped[str | None] = mapped_column(Text)  # cuerpo del aviso (detalle)
    url: Mapped[str | None] = mapped_column(String(1024))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR)  # GENERATED (0005)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DnuTracking(Base):
    """Seguimiento del tratamiento bicameral de un DNU (Comisión Bicameral)."""

    __tablename__ = "dnu_tracking"
    __table_args__ = (Index("ix_dnu_estado", "estado_bicameral"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    norma_id: Mapped[int] = mapped_column(
        ForeignKey("norma.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    estado_bicameral: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pendiente"
    )  # sin_tratamiento | pendiente | dictaminado | aprobado | rechazado
    fecha_dictamen: Mapped[date | None] = mapped_column(Date)
    plazo_limite: Mapped[date | None] = mapped_column(Date)
    notas: Mapped[str | None] = mapped_column(Text)
    dictamen_url: Mapped[str | None] = mapped_column(String(1024))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # crudo del dictamen (HCDN)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    norma: Mapped[Norma] = relationship(back_populates="dnu_tracking")


class Alerta(Base):
    """Suscripción de monitoreo por keywords (+ sectores opcionales), ligada a workspace.

    Reemplaza el `useState` efímero del frontend mock. El worker cruza las normas
    contra estas alertas y registra cada match en `alerta_match`.

    `keywords`/`sectores` son listas (OR entre sí): la alerta matchea una norma
    si pega ALGUNA keyword (FTS español) y la norma cae en ALGUNO de los sectores
    (o cualquiera, si la lista está vacía). `anchor_at` es el piso temporal: solo
    se notifican normas con `ingested_at >= anchor_at` (default = alta de la
    alerta; se reancla a now() al editar el criterio). Sin esto, una alerta nueva
    spamearía con todo el corpus histórico.
    """

    __tablename__ = "alerta"
    __table_args__ = (
        Index("ix_alerta_workspace", "workspace_id"),
        Index("ix_alerta_activa", "activa"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
    keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    sectores: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    anchor_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_match_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    matches: Mapped[list[AlertaMatch]] = relationship(
        back_populates="alerta", cascade="all, delete-orphan"
    )


class AlertaMatch(Base):
    """Una norma que matcheó una alerta. Idempotente por (alerta_id, norma_id)."""

    __tablename__ = "alerta_match"
    __table_args__ = (
        UniqueConstraint("alerta_id", "norma_id", name="uq_match_alerta_norma"),
        Index("ix_match_alerta", "alerta_id"),
        Index("ix_match_notified", "notified"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    alerta_id: Mapped[int] = mapped_column(
        ForeignKey("alerta.id", ondelete="CASCADE"), nullable=False
    )
    norma_id: Mapped[int] = mapped_column(
        ForeignKey("norma.id", ondelete="CASCADE"), nullable=False
    )
    notified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    matched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    alerta: Mapped[Alerta] = relationship(back_populates="matches")


# ───────────────────────── Fase 2 — multi-tenant (B2C/B2B) ─────────────────────────


class AppUser(Base):
    """Identidad de usuario final (una fila por cuenta Google)."""

    __tablename__ = "app_user"
    __table_args__ = (Index("ix_app_user_provider_id", "provider", "provider_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    image_url: Mapped[str | None] = mapped_column(String(1024))
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="google")
    provider_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Workspace(Base):
    """Tenant. Cada usuario tiene al menos uno (su workspace personal al firmar in).

    Modelo híbrido B2C/B2B: un usuario individual usa su workspace personal;
    una organización invita miembros al mismo workspace. `plan` queda como
    placeholder para una futura capa de billing (hoy todos 'free').
    """

    __tablename__ = "workspace"
    __table_args__ = (Index("ix_workspace_plan", "plan"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    seat_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    sectores_interes: Mapped[list[str] | None] = mapped_column(JSONB)  # onboarding
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkspaceMember(Base):
    __tablename__ = "workspace_member"
    __table_args__ = (
        CheckConstraint("role IN ('owner', 'admin', 'viewer')", name="ck_member_role"),
        UniqueConstraint("workspace_id", "user_id", name="uq_member_unique"),
        Index("ix_member_user", "user_id"),
        Index("ix_member_workspace", "workspace_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="viewer")
    invited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkspaceInvitation(Base):
    __tablename__ = "workspace_invitation"
    __table_args__ = (
        CheckConstraint("role IN ('owner', 'admin', 'viewer')", name="ck_invite_role"),
        Index("ix_invite_workspace_email", "workspace_id", "email"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="viewer")
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditLog(Base):
    """Bitácora append-only por workspace (login, invite, member, etc.)."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_workspace_created", "workspace_id", "created_at"),
        Index("ix_audit_action", "action"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE")
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(128))
    params: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
