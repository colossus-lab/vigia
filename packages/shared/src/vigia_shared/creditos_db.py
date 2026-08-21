"""Persistencia del contador de créditos.

Separado de `vigia_shared.creditos` (que es aritmética pura) porque acá hay
I/O: lo usan la API para mostrar el saldo y el worker para cobrarlo.

Todas las funciones reciben la `session` en vez de abrirla: el worker cobra
dentro de una corrida que ya tiene la suya, y la API dentro del request.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_UPSERT = text(
    """
    INSERT INTO credito_contador (workspace_id, periodo, micros)
    VALUES (:ws, :periodo, :micros)
    ON CONFLICT (workspace_id, periodo) DO UPDATE
       SET micros = credito_contador.micros + excluded.micros,
           updated_at = now()
    RETURNING micros
    """
)


async def sumar(session: AsyncSession, workspace_id: int, periodo: str, micros: int) -> int:
    """Suma consumo y devuelve el acumulado del período.

    El `ON CONFLICT DO UPDATE` suma del lado del motor a propósito: un
    read-modify-write desde Python perdería débitos cuando dos corridas del
    matcher se pisan. Es el equivalente del `ADD` atómico de DynamoDB que usa
    el sistema de Políticas Públicas.
    """
    if micros <= 0:
        return await leer(session, workspace_id, periodo)
    row = await session.execute(
        _UPSERT, {"ws": workspace_id, "periodo": periodo, "micros": int(micros)}
    )
    return int(row.scalar_one())


async def leer(session: AsyncSession, workspace_id: int, periodo: str) -> int:
    """Consumo acumulado. Sin fila todavía = 0 (no es un error: es el mes nuevo)."""
    row = await session.execute(
        text(
            "SELECT micros FROM credito_contador "
            "WHERE workspace_id = :ws AND periodo = :periodo"
        ),
        {"ws": workspace_id, "periodo": periodo},
    )
    return int(row.scalar_one_or_none() or 0)


async def leer_varios(
    session: AsyncSession, claves: list[tuple[int, str]]
) -> dict[tuple[int, str], int]:
    """Consumo de varios (workspace, período) en una sola query.

    El matcher toca hasta ~100 workspaces por corrida; sin esto serían 100
    round-trips antes de mandar un mail.
    """
    if not claves:
        return {}
    rows = (
        await session.execute(
            # Los CAST explícitos no son decorativos: sin ellos asyncpg manda los
            # arrays como `unknown` y Postgres corta con "function unnest(unknown)
            # is not unique".
            text(
                "SELECT workspace_id, periodo, micros FROM credito_contador "
                "WHERE (workspace_id, periodo) IN ("
                "  SELECT * FROM unnest(CAST(:ws AS bigint[]), CAST(:periodos AS varchar[]))"
                ")"
            ),
            {"ws": [c[0] for c in claves], "periodos": [c[1] for c in claves]},
        )
    ).all()
    encontrados = {(int(r[0]), r[1]): int(r[2]) for r in rows}
    return {clave: encontrados.get(clave, 0) for clave in claves}


async def tomar_aviso_agotado(session: AsyncSession, workspace_id: int, periodo: str) -> bool:
    """True si a este workspace le toca el mail de "te quedaste sin créditos".

    La marca se pone en el MISMO statement que la lee, así dos corridas
    concurrentes del matcher no mandan el aviso dos veces. Devuelve False si ya
    se avisó en este período — sin esto saldría un mail por hora, avisándole a
    alguien que dejamos de mandarle mails.

    Como la fila lleva el período en la PK, la marca se limpia sola al rotar.
    """
    row = await session.execute(
        text(
            """
            INSERT INTO credito_contador (workspace_id, periodo, micros, aviso_agotado_at)
            VALUES (:ws, :periodo, 0, now())
            ON CONFLICT (workspace_id, periodo) DO UPDATE
               SET aviso_agotado_at = now()
             WHERE credito_contador.aviso_agotado_at IS NULL
            RETURNING workspace_id
            """
        ),
        {"ws": workspace_id, "periodo": periodo},
    )
    return row.scalar_one_or_none() is not None


async def purgar(session: AsyncSession, periodos_a_conservar: list[str]) -> int:
    """Borra los contadores de períodos viejos. Devuelve cuántas filas borró."""
    if not periodos_a_conservar:
        return 0
    row = await session.execute(
        text("DELETE FROM credito_contador WHERE periodo <> ALL(:vivos)"),
        {"vivos": periodos_a_conservar},
    )
    return int(row.rowcount or 0)
