"""Cobro de créditos en el matcher, contra Postgres real.

Se saltea solo si no hay una base de test a mano. Para correrlo:

    docker run -d --name vigia-tmp -e POSTGRES_USER=vigia -e POSTGRES_PASSWORD=tmp \
      -e POSTGRES_DB=vigia -p 55432:5432 \
      -v "$(pwd -W)/db/init:/docker-entrypoint-initdb.d:ro" pgvector/pgvector:pg16
    export VIGIA_TEST_DATABASE_URL="postgresql+asyncpg://vigia:tmp@localhost:55432/vigia"
    alembic -c db/alembic.ini upgrade head
    pytest apps/workers/tests/test_creditos_matcher.py

Lo que se verifica no es la aritmética (eso está en packages/shared/tests) sino
las cuatro reglas que solo se pueden romper acá: que un digest cobre, que sin
cupo el match igual quede registrado, que el aviso de "sin créditos" salga UNA
vez por período, y que un backfill no cobre ni avise.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

VIGIA_TEST_DB = os.environ.get("VIGIA_TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not VIGIA_TEST_DB, reason="sin VIGIA_TEST_DATABASE_URL: se saltea el test con DB"
)

WS = 91_001
PERIODO_LIBRE = "9999-01"  # período imposible, para no pisar datos reales


@pytest.fixture(autouse=True)
def _db_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", VIGIA_TEST_DB)


@pytest.fixture
def enviados(monkeypatch):
    """Intercepta Resend. Devuelve la lista de mails que se habrían mandado."""
    caja: list[dict] = []

    def _fake(**kw):
        caja.append(kw)
        return {"sent": True}

    import vigia_workers.alerts as al

    monkeypatch.setattr(al, "send_email", _fake)
    return caja


async def _seed(cupo_agotado: bool = False):
    from vigia_shared import creditos as cred
    from vigia_shared import creditos_db as cdb
    from vigia_shared.db import session_scope

    async with session_scope() as s:
        await s.execute(text("DELETE FROM alerta_match WHERE alerta_id = :a"), {"a": WS})
        await s.execute(text("DELETE FROM alerta WHERE workspace_id = :w"), {"w": WS})
        await s.execute(text("DELETE FROM credito_contador WHERE workspace_id = :w"), {"w": WS})
        await s.execute(text("DELETE FROM workspace_member WHERE workspace_id = :w"), {"w": WS})
        await s.execute(text("DELETE FROM app_user WHERE id = :u"), {"u": WS})
        await s.execute(text("DELETE FROM workspace WHERE id = :w"), {"w": WS})
        await s.execute(text("DELETE FROM norma WHERE source_id = 9901"))
        await s.execute(text("DELETE FROM source_catalog WHERE id = 9901"))

        await s.execute(
            text(
                "INSERT INTO source_catalog (id, code, name, kind) "
                "VALUES (9901, 'test-creditos', 'Test', 'test')"
            )
        )
        # search_vector es GENERATED: INSERT crudo, sin esa columna.
        for i in range(1, 4):
            await s.execute(
                text(
                    "INSERT INTO norma (source_id, external_id, tipo, numero, titulo, "
                    "jurisdiccion, estado, ingested_at) VALUES "
                    "(9901, :e, 'LEY', :n, 'Ley sobre energia electrica', "
                    "'nacional', 'Publicada', now())"
                ),
                {"e": f"cred-{i}", "n": str(i)},
            )
        await s.execute(
            text("INSERT INTO workspace (id, slug, name, plan) VALUES (:w, :s, 'Test', 'free')"),
            {"w": WS, "s": f"test-cred-{WS}"},
        )
        await s.execute(
            text(
                "INSERT INTO app_user (id, email, name, provider, provider_id) "
                "VALUES (:u, :e, 'Test', 'google', :p)"
            ),
            {"u": WS, "e": f"cred{WS}@test.local", "p": f"g{WS}"},
        )
        # Id explícito: la secuencia de `alerta` puede venir pisada por otros
        # datos de la base de test, y un id fijo hace el seed reejecutable.
        await s.execute(
            text(
                "INSERT INTO alerta (id, workspace_id, user_id, activa, keywords, sectores, anchor_at) "
                "VALUES (:a, :w, :u, true, CAST('[\"energia\"]' AS jsonb), CAST('[]' AS jsonb), "
                "now() - interval '1 day')"
            ),
            {"a": WS, "w": WS, "u": WS},
        )
        if cupo_agotado:
            await cdb.sumar(
                s,
                WS,
                cred.periodo_de("free"),
                cred.CUPO_POR_DEFECTO * cred.MICROS_POR_CREDITO,
            )


async def _saldo() -> int:
    from vigia_shared import creditos as cred
    from vigia_shared import creditos_db as cdb
    from vigia_shared.db import session_scope

    async with session_scope() as s:
        return await cdb.leer(s, WS, cred.periodo_de("free"))


async def _reset_matches():
    from vigia_shared.db import session_scope

    async with session_scope() as s:
        await s.execute(text("DELETE FROM alerta_match WHERE alerta_id = :a"), {"a": WS})


async def test_un_digest_cobra_un_credito(enviados):
    from vigia_shared import creditos as cred
    from vigia_workers.alerts import _match_all

    await _seed()
    r = await _match_all(notify=True)

    assert r["new_matches"] == 3
    assert r["emails"] == 1  # las 3 normas viajan en UN digest, no en tres
    assert r["omitidos"] == 0
    assert len(enviados) == 1
    assert await _saldo() == cred.micros_de("digest")


async def test_sin_cupo_no_manda_el_mail_pero_registra_el_match(enviados):
    from vigia_workers.alerts import _match_all

    await _seed(cupo_agotado=True)
    r = await _match_all(notify=True)

    assert r["emails"] == 0
    assert r["omitidos"] == 1
    # Lo que NO se pierde: el match queda, y se ve en la app.
    assert r["new_matches"] == 3
    # El único mail que sale es el aviso de que se acabaron.
    assert len(enviados) == 1
    assert "créditos" in enviados[0]["subject"]


async def test_el_aviso_sale_una_sola_vez_por_periodo(enviados):
    """Sin esto saldría un aviso por hora: un mail cada hora para avisarle a
    alguien que dejamos de mandarle mails."""
    from vigia_workers.alerts import _match_all

    await _seed(cupo_agotado=True)
    primera = await _match_all(notify=True)
    assert primera["avisados"] == 1

    enviados.clear()
    await _reset_matches()
    segunda = await _match_all(notify=True)

    assert segunda["omitidos"] == 1  # sigue sin mandar el digest
    assert segunda["avisados"] == 0  # pero NO vuelve a avisar
    assert enviados == []


async def test_el_aviso_no_consume_credito(enviados):
    from vigia_workers.alerts import _match_all

    await _seed(cupo_agotado=True)
    antes = await _saldo()
    await _match_all(notify=True)
    assert await _saldo() == antes


async def test_nivel_pleno_manda_sin_importar_el_cupo(enviados):
    from vigia_shared.db import session_scope
    from vigia_workers.alerts import _match_all

    await _seed(cupo_agotado=True)
    async with session_scope() as s:
        await s.execute(
            text("UPDATE workspace SET plan = 'pleno' WHERE id = :w"), {"w": WS}
        )
    r = await _match_all(notify=True)

    assert r["emails"] == 1
    assert r["omitidos"] == 0


async def test_backfill_no_cobra_ni_avisa(enviados):
    """`notify=False` es lo que evita que dar de alta una fuente nueva spamee a
    todo el mundo. Tampoco puede vaciarle el cupo a nadie."""
    from vigia_workers.alerts import _match_all

    await _seed(cupo_agotado=True)
    antes = await _saldo()
    r = await _match_all(notify=False)

    assert r["new_matches"] == 3  # los matches sí se registran
    assert r["emails"] == 0
    assert r["avisados"] == 0
    assert enviados == []
    assert await _saldo() == antes


async def test_los_matches_quedan_marcados_como_notificados(enviados):
    """El UPDATE de `notified` está scopeado a los ids de esta corrida; antes era
    global y también marcaba los que otra corrida acababa de insertar."""
    from vigia_shared.db import session_scope
    from vigia_workers.alerts import _match_all

    await _seed()
    await _match_all(notify=True)
    async with session_scope() as s:
        pendientes = await s.scalar(
            text("SELECT count(*) FROM alerta_match WHERE notified = false")
        )
    assert pendientes == 0
