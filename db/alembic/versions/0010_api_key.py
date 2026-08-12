"""api_key — credenciales de máquina para la API pública /v1

Revision ID: 0010_api_key
Revises: 0009_norma_updated_index
Create Date: 2026-08-12

Del secreto solo se guarda el SHA-256. `uq_api_key_hash` no es solo integridad:
es el índice por el que se resuelve CADA request autenticado de /v1, así que
verificar una key es un lookup y no un scan de la tabla.

`revoked_at` nullable en vez de borrar la fila: una key revocada sigue
explicando lo que quedó en el audit log.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_api_key"
down_revision: Union[str, None] = "0009_norma_updated_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_key",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.BigInteger(), nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("prefix", sa.String(length=24), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_api_key_hash"),
    )
    op.create_index("ix_api_key_workspace", "api_key", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_api_key_workspace", table_name="api_key")
    op.drop_table("api_key")
