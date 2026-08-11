"""norma — índice para la sincronización incremental de /v1

Revision ID: 0009_norma_updated_index
Revises: 0008_norma_feed_index
Create Date: 2026-08-11

`GET /v1/normas?updated_since=...` recorre el corpus por `updated_at ASC, id ASC`
y pagina por keyset: cada página es una comparación de tupla
`(updated_at, id) > (:u0, :i0)` con LIMIT. Sin un índice que calque ese orden,
la comparación no sirve como punto de arranque y cada página vuelve a escanear
las ~543k filas — el mismo problema que arregló 0008 para el feed.

Se incluye `id` en el índice y no solo `updated_at`: el desempate por id es lo
que hace que el cursor sea determinístico cuando varias normas comparten
timestamp, que con la ingesta por lotes es el caso normal y no el raro.

CONCURRENTLY (fuera de transacción) para no bloquear a la ingesta, e
`IF NOT EXISTS` para que sea re-ejecutable.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009_norma_updated_index"
down_revision: Union[str, None] = "0008_norma_feed_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_norma_updated "
            "ON norma (updated_at, id)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_norma_updated")
