"""credito_contador + workspace.aporte — medidor de consumo por workspace

Revision ID: 0011_creditos
Revises: 0010_api_key
Create Date: 2026-08-21

No hay tabla de saldo ni ledger: hay un contador cuya PK incluye el período
("2026-08", o "2026-08q1" para el nivel base, que recarga por quincena). El
saldo se deriva (cupo - usados). Consecuencias buscadas:

- El reset del período sale gratis: el 1° se escribe en una fila nueva. No hay
  job de reset que se pueda quedar colgado.
- Cambiar de nivel a mitad de mes arranca en cero solo, porque cambia la clave.
- `aviso_agotado_at` ("ya le avisamos por mail que se quedó sin crédito") vive
  acá y no en `workspace` por lo mismo: se limpia sola al rotar el período.

Se guarda plata (micro-dólares enteros), no créditos: el crédito es una capa de
presentación y cambiar su valor es cambiar una constante, sin backfill.

`workspace.plan` ya existía como placeholder de billing y pasa a valer
free|base|pleno; `aporte` guarda solo los metadatos (desde/hasta/origen), que
escribe el script de ops y nunca la web.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_creditos"
down_revision: Union[str, None] = "0010_api_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credito_contador",
        sa.Column("workspace_id", sa.BigInteger(), nullable=False),
        sa.Column("periodo", sa.String(length=16), nullable=False),
        sa.Column("micros", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("aviso_agotado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("workspace_id", "periodo"),
    )
    op.add_column("workspace", sa.Column("aporte", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("workspace", "aporte")
    op.drop_table("credito_contador")
