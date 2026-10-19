"""Ventana por fecha propia de la norma en el matcher, contra Postgres real.

Se saltea solo si no hay una base de test a mano (receta en
`test_creditos_matcher.py`).

Lo que importa: una carga histórica entra con `ingested_at` de hoy, así que el
ancla de la alerta (que mira `ingested_at`) no la frena. Sin la ventana por
`fecha_publicacion`, una norma de 2006 cargada hoy era "noticia" para el
matcher, y borrar su match lo hacía volver en la corrida siguiente — con mail.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

VIGIA_TEST_DB = os.environ.get("VIGIA_TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not VIGIA_TEST_DB, reason="sin VIGIA_TEST_DATABASE_URL: se saltea el test con DB"
)

WS = 91_002
SRC = 9902


@pytest.fixture(autouse=True)
def _db_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", VIGIA_TEST_DB)


async def _limpiar():
    from vigia_shared.db import session_scope

    async with session_scope() as s:
        await s.execute(text("DELETE FROM alerta_match WHERE alerta_id = :a"), {"a": WS})
        await s.execute(text("DELETE FROM alerta WHERE workspace_id = :w"), {"w": WS})
        await s.execute(text("DELETE FROM workspace_member WHERE workspace_id = :w"), {"w": WS})
        await s.execute(text("DELETE FROM app_user WHERE id = :u"), {"u": WS})
        await s.execute(text("DELETE FROM workspace WHERE id = :w"), {"w": WS})
        await s.execute(text("DELETE FROM norma WHERE source_id = :s"), {"s": SRC})
        await s.execute(text("DELETE FROM source_catalog WHERE id = :s"), {"s": SRC})


@pytest.fixture(autouse=True)
async def _sin_rastros():
    """Una alerta o normas que queden en la base matchean contra los otros tests
    del matcher (comparten la base): se limpia también al salir."""
    yield
    await _limpiar()


@pytest.fixture
def enviados(monkeypatch):
    caja: list[dict] = []

    def _fake(**kw):
        caja.append(kw)
        return {"sent": True}

    import vigia_workers.alerts as al

    monkeypatch.setattr(al, "send_email", _fake)
    return caja


# external_id -> días de antigüedad de fecha_publicacion (None = sin fecha)
_NORMAS = {
    "hoy": 0,
    "reciente": 30,
    "borde": 120,      # justo en el límite: entra
    "vieja": 121,      # un día afuera
    "historica": 7300,  # ~2006, como el backfill del Senado
    "sin-fecha": None,
}


async def _seed():
    from vigia_shared.db import session_scope

    await _limpiar()
    async with session_scope() as s:
        await s.execute(
            text("INSERT INTO source_catalog (id, code, name, kind) VALUES (:s, 'test-ventana', 'Test', 'test')"),
            {"s": SRC},
        )
        # Todas cargadas HOY (después del ancla): lo único que las distingue es
        # su fecha propia. search_vector es GENERATED: INSERT crudo, sin ella.
        for ext, dias in _NORMAS.items():
            await s.execute(
                text(
                    "INSERT INTO norma (source_id, external_id, tipo, titulo, jurisdiccion, "
                    "fecha_publicacion, ingested_at) VALUES (:s, :e, 'PROYECTO', "
                    "'Proyecto sobre biocombustibles ventanilla', 'nacional', "
                    "CASE WHEN CAST(:d AS integer) IS NULL THEN NULL "
                    "     ELSE CURRENT_DATE - CAST(:d AS integer) END, now())"
                ),
                {"s": SRC, "e": f"ventana-{ext}", "d": dias},
            )
        await s.execute(
            text("INSERT INTO workspace (id, slug, name, plan) VALUES (:w, :s, 'Test', 'pleno')"),
            {"w": WS, "s": f"test-ventana-{WS}"},
        )
        await s.execute(
            text(
                "INSERT INTO app_user (id, email, name, provider, provider_id) "
                "VALUES (:u, :e, 'Test', 'google', :p)"
            ),
            {"u": WS, "e": f"ventana{WS}@test.local", "p": f"g{WS}"},
        )
        await s.execute(
            text(
                "INSERT INTO alerta (id, workspace_id, user_id, activa, keywords, sectores, anchor_at) "
                "VALUES (:a, :w, :u, true, CAST('[\"biocombustibles\"]' AS jsonb), CAST('[]' AS jsonb), "
                "now() - interval '1 day')"
            ),
            {"a": WS, "w": WS, "u": WS},
        )


async def _matcheadas() -> set[str]:
    from vigia_shared.db import session_scope

    async with session_scope() as s:
        rows = await s.execute(
            text(
                "SELECT n.external_id FROM alerta_match m JOIN norma n ON n.id = m.norma_id "
                "WHERE m.alerta_id = :a"
            ),
            {"a": WS},
        )
        return {r[0].removeprefix("ventana-") for r in rows}


async def test_una_carga_historica_no_dispara_la_alerta(enviados):
    from vigia_workers.alerts import _match_all

    await _seed()
    await _match_all(notify=True)

    assert await _matcheadas() == {"hoy", "reciente", "borde", "sin-fecha"}


async def test_borrar_los_matches_viejos_no_los_hace_volver(enviados):
    """El motivo del cambio: antes, borrar un match de una norma histórica la
    devolvía al matcher siguiente, y esa vez con mail."""
    from vigia_shared.db import session_scope
    from vigia_workers.alerts import _match_all

    await _seed()
    # Simula el estado de prod después de un backfill con notify=False: las
    # históricas quedaron matcheadas (y marcadas) antes de existir la ventana.
    async with session_scope() as s:
        await s.execute(
            text(
                "INSERT INTO alerta_match (alerta_id, norma_id, notified) "
                "SELECT :a, id, true FROM norma WHERE source_id = :s "
                "AND external_id IN ('ventana-vieja', 'ventana-historica')"
            ),
            {"a": WS, "s": SRC},
        )
        await s.execute(
            text(
                "DELETE FROM alerta_match WHERE alerta_id = :a AND norma_id IN "
                "(SELECT id FROM norma WHERE source_id = :s "
                " AND external_id IN ('ventana-vieja', 'ventana-historica'))"
            ),
            {"a": WS, "s": SRC},
        )

    r = await _match_all(notify=True)

    assert {"vieja", "historica"}.isdisjoint(await _matcheadas())
    # El digest que sí sale lleva solo las normas dentro de la ventana.
    assert r["new_matches"] == 4
    assert len(enviados) == 1
