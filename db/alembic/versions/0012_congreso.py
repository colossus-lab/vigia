"""congreso — actividad de Senado y Diputados + norma.expedientes

Revision ID: 0012_congreso
Revises: 0011_creditos
Create Date: 2026-10-19

Lo que pasa en el Congreso (votaciones, sesiones, agenda de comisiones) va en
tablas propias y NO en `norma`, por el mismo motivo que `aviso_societario`: el
feed, las stats y las alertas FTS se contaminarían con cosas que no son normas.

La llave del cruce con los proyectos es el expediente en forma canónica
(`vigia_shared.expedientes`). Va como `text[]` con GIN en las dos puntas porque
un proyecto tiene un expediente por cámara y una votación o reunión puede
tratar varios: el cruce es por solapamiento (`&&`).

`voto` guarda bloque y distrito AL MOMENTO de votar: el bloque de un legislador
cambia con los años y el histórico tiene que contar lo que pasó, no lo de hoy.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision: str = "0012_congreso"
down_revision: Union[str, None] = "0011_creditos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CAMARA = "camara IN ('S', 'D')"


def _expedientes() -> sa.Column:
    return sa.Column(
        "expedientes", ARRAY(sa.String(32)), nullable=False, server_default=sa.text("'{}'")
    )


def _ingested_at() -> sa.Column:
    return sa.Column(
        "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    # ── norma.expedientes: la punta "proyecto" del cruce ──────────────────────
    op.add_column("norma", _expedientes())
    op.create_index("ix_norma_expedientes", "norma", ["expedientes"], postgresql_using="gin")

    op.create_table(
        "legislador",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("camara", sa.String(1), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("nombre", sa.String(255), nullable=False),
        sa.Column("bloque", sa.String(255)),
        sa.Column("distrito", sa.String(128)),
        sa.Column("mandato_desde", sa.Date()),
        sa.Column("mandato_hasta", sa.Date()),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("raw", JSONB()),
        _ingested_at(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(_CAMARA, name="ck_legislador_camara"),
        sa.UniqueConstraint("camara", "external_id", name="uq_legislador_camara_ext"),
    )
    op.create_index("ix_legislador_bloque", "legislador", ["camara", "bloque"])

    op.create_table(
        "congreso_sesion",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("camara", sa.String(1), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("tipo", sa.String(128)),
        sa.Column("periodo", sa.Integer()),
        sa.Column("reunion", sa.Integer()),
        sa.Column("numero_sesion", sa.Integer()),
        sa.Column("url", sa.String(1024)),
        sa.Column("url_taquigrafica", sa.String(1024)),
        sa.Column("url_diario", sa.String(1024)),
        sa.Column("raw", JSONB()),
        _ingested_at(),
        sa.CheckConstraint(_CAMARA, name="ck_sesion_camara"),
        sa.UniqueConstraint("camara", "external_id", name="uq_sesion_camara_ext"),
    )
    op.create_index("ix_sesion_fecha", "congreso_sesion", ["fecha"])

    op.create_table(
        "votacion",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("camara", sa.String(1), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column(
            "sesion_id", sa.BigInteger(), sa.ForeignKey("congreso_sesion.id", ondelete="SET NULL")
        ),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False),
        sa.Column("numero_acta", sa.String(32)),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("etapa", sa.String(64)),       # EN GENERAL | EN PARTICULAR | ...
        sa.Column("mayoria", sa.String(128)),
        sa.Column("resultado", sa.String(64)),   # AFIRMATIVO | NEGATIVO | ...
        sa.Column("afirmativos", sa.Integer()),
        sa.Column("negativos", sa.Integer()),
        sa.Column("abstenciones", sa.Integer()),
        sa.Column("ausentes", sa.Integer()),
        _expedientes(),
        sa.Column("ordenes_del_dia", ARRAY(sa.String(32)), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("url", sa.String(1024)),
        sa.Column("url_pdf", sa.String(1024)),
        sa.Column("video_url", sa.String(1024)),
        sa.Column("raw", JSONB()),
        _ingested_at(),
        sa.CheckConstraint(_CAMARA, name="ck_votacion_camara"),
        sa.UniqueConstraint("camara", "external_id", name="uq_votacion_camara_ext"),
    )
    op.create_index("ix_votacion_fecha", "votacion", ["fecha"])
    op.create_index("ix_votacion_sesion", "votacion", ["sesion_id"])
    op.create_index("ix_votacion_expedientes", "votacion", ["expedientes"], postgresql_using="gin")
    op.execute(
        """
        ALTER TABLE votacion ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (setweight(to_tsvector('spanish', coalesce(titulo, '')), 'A')) STORED
        """
    )
    op.create_index("ix_votacion_search_vector", "votacion", ["search_vector"], postgresql_using="gin")

    op.create_table(
        "voto",
        sa.Column(
            "votacion_id", sa.BigInteger(),
            sa.ForeignKey("votacion.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "legislador_id", sa.BigInteger(),
            sa.ForeignKey("legislador.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column("voto", sa.String(16), nullable=False),
        sa.Column("bloque", sa.String(255)),
        sa.Column("distrito", sa.String(128)),
        sa.CheckConstraint(
            "voto IN ('afirmativo', 'negativo', 'abstencion', 'ausente', 'presidente', 'otro')",
            name="ck_voto_valor",
        ),
    )
    # "Cómo votó X": recorre por legislador, no por votación.
    op.create_index("ix_voto_legislador", "voto", ["legislador_id"])

    op.create_table(
        "asunto_tratado",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("camara", sa.String(1), nullable=False),
        sa.Column(
            "sesion_id", sa.BigInteger(),
            sa.ForeignKey("congreso_sesion.id", ondelete="CASCADE"), nullable=False,
        ),
        # Clave natural dentro de la sesión. Texto (no array) porque un asunto
        # puede no tener expediente (homenajes, mociones) y entonces lo
        # identifica la O.D. o el orden en el boletín.
        sa.Column("clave", sa.String(128), nullable=False),
        _expedientes(),
        sa.Column("orden_del_dia", sa.String(32)),
        sa.Column("tipo", sa.String(64)),
        sa.Column("sumario", sa.Text()),
        sa.Column("resultado", sa.String(255)),
        sa.Column("raw", JSONB()),
        _ingested_at(),
        sa.CheckConstraint(_CAMARA, name="ck_asunto_camara"),
        sa.UniqueConstraint("sesion_id", "clave", name="uq_asunto_sesion_clave"),
    )
    op.create_index("ix_asunto_expedientes", "asunto_tratado", ["expedientes"], postgresql_using="gin")

    op.create_table(
        "reunion_comision",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("camara", sa.String(1), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("fecha_hora", sa.DateTime(timezone=True), nullable=False),
        sa.Column("comision", sa.String(512), nullable=False),
        sa.Column("sala", sa.String(255)),
        sa.Column("tipo", sa.String(128)),
        sa.Column("temario", sa.Text()),
        _expedientes(),
        sa.Column("url_citacion", sa.String(1024)),
        sa.Column("raw", JSONB()),
        _ingested_at(),
        sa.CheckConstraint(_CAMARA, name="ck_reunion_camara"),
        sa.UniqueConstraint("camara", "external_id", name="uq_reunion_camara_ext"),
    )
    op.create_index("ix_reunion_fecha", "reunion_comision", ["fecha_hora"])
    op.create_index("ix_reunion_expedientes", "reunion_comision", ["expedientes"], postgresql_using="gin")
    op.execute(
        """
        ALTER TABLE reunion_comision ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('spanish', coalesce(comision, '')), 'A') ||
            setweight(to_tsvector('spanish', coalesce(temario, '')), 'B')
        ) STORED
        """
    )
    op.create_index(
        "ix_reunion_search_vector", "reunion_comision", ["search_vector"], postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_table("reunion_comision")
    op.drop_table("asunto_tratado")
    op.drop_table("voto")
    op.drop_table("votacion")
    op.drop_table("congreso_sesion")
    op.drop_table("legislador")
    op.drop_index("ix_norma_expedientes", table_name="norma")
    op.drop_column("norma", "expedientes")
