"""norma — índice compuesto para el orden del feed

Revision ID: 0008_norma_feed_index
Revises: 0007_norma_emisor
Create Date: 2026-07-24

El feed (`GET /normas`) ordena por `fecha_publicacion DESC NULLS LAST, id DESC`.
`ix_norma_fecha` es ASC y la columna es nullable, así que un scan hacia atrás
daría NULLS FIRST: Postgres no lo podía usar y resolvía cada request con un
Parallel Seq Scan de las ~543k filas + top-N heapsort (~5,9 s medidos en prod,
~900 MB leídos de disco). Este índice calca el ORDER BY exacto, incluido el
desempate por `id`, para que el orden salga del índice y el LIMIT corte ahí.

Se crea CONCURRENTLY (fuera de transacción) para no bloquear escrituras de la
ingesta; `IF NOT EXISTS` lo hace re-ejecutable y no falla en los entornos donde
ya se creó a mano.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0008_norma_feed_index"
down_revision: Union[str, None] = "0007_norma_emisor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_norma_feed "
            "ON norma (fecha_publicacion DESC NULLS LAST, id DESC)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_norma_feed")
