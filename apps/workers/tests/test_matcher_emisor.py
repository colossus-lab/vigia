"""Alertas por autoridad (`emisores`) en el matcher, contra Postgres real.

Se saltea solo si no hay una base de test a mano (receta en
`test_creditos_matcher.py`).

Lo que importa: `emisores` es OR dentro de la lista y AND con keywords y
sectores. Una alerta solo con `emisores=["CNDC"]` trae todo lo que dicta la CNDC
y nada más; sumarle una keyword la angosta, no la ensancha.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

VIGIA_TEST_DB = os.environ.get("VIGIA_TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not VIGIA_TEST_DB, reason="sin VIGIA_TEST_DATABASE_URL: se saltea el test con DB"
)

WS = 91_003
SRC = 9903
SOLO_EMISOR = WS        # alerta: emisores=["CNDC"]
EMISOR_Y_KW = WS + 1    # alerta: emisores=["CNDC"] + keyword "concentración"


@pytest.fixture(autouse=True)
def _db_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", VIGIA_TEST_DB)


async def _limpiar():
    from vigia_shared.db import session_scope

    async with session_scope() as s:
        await s.execute(
            text("DELETE FROM alerta_match WHERE alerta_id IN (:a, :b)"),
            {"a": SOLO_EMISOR, "b": EMISOR_Y_KW},
        )
        await s.execute(text("DELETE FROM alerta WHERE workspace_id = :w"), {"w": WS})
        await s.execute(text("DELETE FROM workspace_member WHERE workspace_id = :w"), {"w": WS})
        await s.execute(text("DELETE FROM app_user WHERE id = :u"), {"u": WS})
        await s.execute(text("DELETE FROM workspace WHERE id = :w"), {"w": WS})
        await s.execute(text("DELETE FROM norma WHERE source_id = :s"), {"s": SRC})
        await s.execute(text("DELETE FROM source_catalog WHERE id = :s"), {"s": SRC})


@pytest.fixture(autouse=True)
async def _sin_rastros():
    """Las alertas y normas que queden en la base matchean contra los otros tests
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


# external_id -> (emisor, título)
_NORMAS = {
    "cndc-concentracion": ("CNDC", "Autorízase la operación de concentración económica"),
    "cndc-multa": ("CNDC", "Impónese multa por incumplimiento de notificación"),
    "arca-concentracion": ("ARCA", "Régimen informativo de concentración de operaciones"),
    "sin-emisor": (None, "Operación de concentración económica en el sector lácteo"),
}


async def _seed():
    from vigia_shared.db import session_scope

    await _limpiar()
    async with session_scope() as s:
        await s.execute(
            text("INSERT INTO source_catalog (id, code, name, kind) VALUES (:s, 'test-emisor', 'Test', 'test')"),
            {"s": SRC},
        )
        # search_vector es GENERATED: INSERT crudo, sin ella.
        for ext, (emisor, titulo) in _NORMAS.items():
            await s.execute(
                text(
                    "INSERT INTO norma (source_id, external_id, tipo, titulo, jurisdiccion, "
                    "emisor, fecha_publicacion, ingested_at) VALUES (:s, :e, 'RESOLUCION', "
                    ":t, 'nacional', :em, CURRENT_DATE, now())"
                ),
                {"s": SRC, "e": f"emisor-{ext}", "t": titulo, "em": emisor},
            )
        await s.execute(
            text("INSERT INTO workspace (id, slug, name, plan) VALUES (:w, :s, 'Test', 'pleno')"),
            {"w": WS, "s": f"test-emisor-{WS}"},
        )
        await s.execute(
            text(
                "INSERT INTO app_user (id, email, name, provider, provider_id) "
                "VALUES (:u, :e, 'Test', 'google', :p)"
            ),
            {"u": WS, "e": f"emisor{WS}@test.local", "p": f"g{WS}"},
        )
        for aid, keywords in ((SOLO_EMISOR, "[]"), (EMISOR_Y_KW, '["concentración"]')):
            await s.execute(
                text(
                    "INSERT INTO alerta (id, workspace_id, user_id, activa, keywords, sectores, "
                    "emisores, anchor_at) VALUES (:a, :w, :u, true, CAST(:kw AS jsonb), "
                    "CAST('[]' AS jsonb), CAST('[\"CNDC\"]' AS jsonb), now() - interval '1 day')"
                ),
                {"a": aid, "w": WS, "u": WS, "kw": keywords},
            )


async def _matcheadas(alerta_id: int) -> set[str]:
    from vigia_shared.db import session_scope

    # Filtrado por la fuente del test: una alerta solo por emisor matchea TODA
    # norma CNDC de la base, y la base de test es compartida.
    async with session_scope() as s:
        rows = await s.execute(
            text(
                "SELECT n.external_id FROM alerta_match m JOIN norma n ON n.id = m.norma_id "
                "WHERE m.alerta_id = :a AND n.source_id = :s"
            ),
            {"a": alerta_id, "s": SRC},
        )
        return {r[0].removeprefix("emisor-") for r in rows}


async def test_alerta_solo_por_emisor_trae_todo_lo_del_organismo_y_nada_mas(enviados):
    from vigia_workers.alerts import _match_all

    await _seed()
    await _match_all(notify=True)

    assert await _matcheadas(SOLO_EMISOR) == {"cndc-concentracion", "cndc-multa"}


async def test_emisor_y_keyword_se_combinan_con_and(enviados):
    from vigia_workers.alerts import _match_all

    await _seed()
    await _match_all(notify=True)

    # Ni la de ARCA ni la sin emisor entran aunque peguen la keyword.
    assert await _matcheadas(EMISOR_Y_KW) == {"cndc-concentracion"}


async def test_el_digest_rotula_la_alerta_por_organismo(enviados):
    from vigia_workers.alerts import _match_all

    await _seed()
    await _match_all(notify=True)

    # Un solo digest por (usuario, workspace), con las dos alertas adentro.
    mios = [m for m in enviados if m["to"] == f"emisor{WS}@test.local"]
    assert len(mios) == 1
    assert "organismos: CNDC" in mios[0]["html"]
