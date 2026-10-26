"""alerta — emisores como tercer criterio (alertas por autoridad)

Revision ID: 0013_alerta_emisores
Revises: 0012_congreso
Create Date: 2026-10-25

Agrega `alerta.emisores` (JSONB, lista de claves de `norma.emisor`: CNDC, ARCA,
BCRA, …) para poder armar alertas por quién dicta la norma — por ejemplo, todo lo
de la Autoridad Nacional de la Competencia. OR dentro de la lista, AND con
keywords y sectores. Las alertas existentes quedan con `[]` (sin filtro de
emisor), así que no cambia lo que matchean.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0013_alerta_emisores"
down_revision: Union[str, None] = "0012_congreso"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "alerta",
        sa.Column("emisores", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("alerta", "emisores")
