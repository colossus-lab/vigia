"""`PATCH /alerts/{id}` contra Postgres real: cuándo se reinician los matches.

Se saltea sin una base de test (receta en la docstring de
`apps/workers/tests/test_creditos_matcher.py`).

El form del web manda SIEMPRE las tres listas (keywords, sectores, emisores),
así que si el endpoint tratara "vino el campo" como "cambió el criterio", un
"Guardar" sin tocar nada le borraría a la alerta todo su historial de matches
y la re-anclaría a ahora.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

VIGIA_TEST_DB = os.environ.get("VIGIA_TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not VIGIA_TEST_DB, reason="sin VIGIA_TEST_DATABASE_URL: se saltea el test con DB"
)

WS = 91_004
SRC = 9904


async def _limpiar(s) -> None:
    await s.execute(text("DELETE FROM alerta_match WHERE alerta_id = :a"), {"a": WS})
    await s.execute(text("DELETE FROM alerta WHERE workspace_id = :w"), {"w": WS})
    await s.execute(text("DELETE FROM workspace WHERE id = :w"), {"w": WS})
    await s.execute(text("DELETE FROM norma WHERE source_id = :s"), {"s": SRC})
    await s.execute(text("DELETE FROM source_catalog WHERE id = :s"), {"s": SRC})


@pytest.fixture
async def alerta(monkeypatch):
    """Una alerta CNDC + "concentración" con un match registrado."""
    monkeypatch.setenv("DATABASE_URL", VIGIA_TEST_DB)
    from vigia_api.core import db
    from vigia_shared.db import session_scope

    db._engine = db._sessionmaker = None
    async with session_scope() as s:
        await _limpiar(s)
        await s.execute(
            text("INSERT INTO source_catalog (id, code, name, kind) VALUES (:s, 'test-patch', 'Test', 'test')"),
            {"s": SRC},
        )
        await s.execute(
            text(
                "INSERT INTO norma (id, source_id, external_id, tipo, titulo, jurisdiccion, emisor) "
                "VALUES (:i, :s, 'patch-1', 'RESOLUCION', 'Concentración', 'nacional', 'CNDC')"
            ),
            {"i": WS, "s": SRC},
        )
        await s.execute(
            text("INSERT INTO workspace (id, slug, name, plan) VALUES (:w, :s, 'Test', 'free')"),
            {"w": WS, "s": f"test-patch-{WS}"},
        )
        await s.execute(
            text(
                "INSERT INTO alerta (id, workspace_id, activa, keywords, sectores, emisores, anchor_at) "
                "VALUES (:a, :w, true, CAST('[\"concentración\"]' AS jsonb), CAST('[]' AS jsonb), "
                "CAST('[\"CNDC\", \"BCRA\"]' AS jsonb), '2026-01-01')"
            ),
            {"a": WS, "w": WS},
        )
        await s.execute(
            text("INSERT INTO alerta_match (alerta_id, norma_id, notified) VALUES (:a, :n, true)"),
            {"a": WS, "n": WS},
        )
    yield WS
    async with session_scope() as s:
        await _limpiar(s)
    if db._engine is not None:
        await db._engine.dispose()
    db._engine = db._sessionmaker = None


def _ctx():
    from vigia_api.core.security import WorkspaceContext

    return WorkspaceContext(user_id=0, workspace_id=WS, role="owner", plan="free")


async def _anchor(alerta_id: int):
    from vigia_shared.db import session_scope

    async with session_scope() as s:
        return await s.scalar(text("SELECT anchor_at FROM alerta WHERE id = :a"), {"a": alerta_id})


async def test_guardar_sin_cambios_no_borra_los_matches(alerta):
    from vigia_api.routers.alerts import AlertaPatch, update_alerta

    antes = await _anchor(alerta)
    # Lo que manda el form al apretar "Guardar" sin tocar nada (con otro orden).
    out = await update_alerta(
        alerta,
        AlertaPatch(keywords=["concentración"], sectores=[], emisores=["BCRA", "CNDC"]),
        _ctx(),
    )
    assert out.matches == 1
    assert await _anchor(alerta) == antes


async def test_cambiar_emisores_reinicia_los_matches(alerta):
    from vigia_api.routers.alerts import AlertaPatch, update_alerta

    antes = await _anchor(alerta)
    out = await update_alerta(
        alerta,
        AlertaPatch(keywords=["concentración"], sectores=[], emisores=["CNDC"]),
        _ctx(),
    )
    assert out.emisores == ["CNDC"]
    assert out.matches == 0
    assert await _anchor(alerta) > antes
