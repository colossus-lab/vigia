"""API `/congreso` contra Postgres real.

Se saltea sin una base de test (receta en la docstring de
`apps/workers/tests/test_creditos_matcher.py`). La base se comparte con otros
tests y puede tener datos reales cargados: todo lo sembrado usa ids altos y un
expediente imposible, y se borra al terminar.

Lo que se verifica es lo que los helpers puros no cubren: que el cruce por
expediente traiga el proyecto, que el desglose y las estadísticas salgan del
bloque del acta, y que `GET /normas/{id}` sume el bloque `congreso`.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import text

VIGIA_TEST_DB = os.environ.get("VIGIA_TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not VIGIA_TEST_DB, reason="sin VIGIA_TEST_DATABASE_URL: se saltea el test con DB"
)

BASE = 9_100_000
SRC = 9902
EXP = "9999-OV-2099"  # año y número que ninguna fuente real va a tener
L1, L2, L3 = BASE + 1, BASE + 2, BASE + 3
SES, V1, V2, NORMA, REU = BASE + 1, BASE + 1, BASE + 2, BASE + 1, BASE + 1


async def _limpiar(s) -> None:
    await s.execute(text("DELETE FROM voto WHERE votacion_id IN (:a, :b)"), {"a": V1, "b": V2})
    await s.execute(text("DELETE FROM votacion WHERE id IN (:a, :b)"), {"a": V1, "b": V2})
    await s.execute(text("DELETE FROM reunion_comision WHERE id = :r"), {"r": REU})
    await s.execute(text("DELETE FROM congreso_sesion WHERE id = :s"), {"s": SES})
    await s.execute(text("DELETE FROM legislador WHERE id BETWEEN :a AND :b"), {"a": L1, "b": L3})
    await s.execute(text("DELETE FROM norma WHERE source_id = :s"), {"s": SRC})
    await s.execute(text("DELETE FROM source_catalog WHERE id = :s"), {"s": SRC})


async def _seed() -> None:
    from vigia_shared.db import session_scope

    ayer = datetime.now(timezone.utc) - timedelta(days=1)
    async with session_scope() as s:
        await _limpiar(s)
        await s.execute(
            text(
                "INSERT INTO source_catalog (id, code, name, kind) "
                "VALUES (:s, 'test-congreso', 'Test', 'test')"
            ),
            {"s": SRC},
        )
        # search_vector es GENERATED: INSERT crudo, sin esa columna.
        await s.execute(
            text(
                "INSERT INTO norma (id, source_id, external_id, tipo, numero, titulo, estado, "
                "fecha_publicacion, expedientes) VALUES (:n, :s, 'tc-1', 'PROYECTO', :e, "
                "'Proyecto de prueba', 'En trámite', CURRENT_DATE, CAST(:x AS varchar[]))"
            ),
            {"n": NORMA, "s": SRC, "e": EXP, "x": [EXP]},
        )
        for lid, bloque in ((L1, "BLOQUE A"), (L2, "BLOQUE A"), (L3, "BLOQUE B")):
            await s.execute(
                text(
                    "INSERT INTO legislador (id, camara, external_id, nombre, bloque, distrito) "
                    "VALUES (:i, 'S', :e, :n, :b, 'TEST')"
                ),
                {"i": lid, "e": f"tc-{lid}", "n": f"ZZTEST, {lid}", "b": bloque},
            )
        await s.execute(
            text(
                "INSERT INTO congreso_sesion (id, camara, external_id, fecha, tipo) "
                "VALUES (:i, 'S', 'tc-ses', :f, 'ORDINARIA')"
            ),
            {"i": SES, "f": ayer.date()},
        )
        for vid, minutos in ((V1, 0), (V2, 5)):
            await s.execute(
                text(
                    "INSERT INTO votacion (id, camara, external_id, sesion_id, fecha, titulo, "
                    "resultado, afirmativos, negativos, expedientes) VALUES "
                    "(:i, 'S', :e, :s, :f, 'Votación de prueba', 'afirmativo', 2, 1, CAST(:x AS varchar[]))"
                ),
                {
                    "i": vid, "e": f"tc-{vid}", "s": SES, "f": ayer + timedelta(minutes=minutos),
                    "x": [EXP] if vid == V1 else [],
                },
            )
        votos = [
            # V1: el bloque A vota unido y B en contra.
            (V1, L1, "afirmativo", "BLOQUE A"),
            (V1, L2, "afirmativo", "BLOQUE A"),
            (V1, L3, "negativo", "BLOQUE B"),
            # V2: el bloque A empata (no cuenta para el alineamiento) y L3 falta.
            (V2, L1, "negativo", "BLOQUE A"),
            (V2, L2, "afirmativo", "BLOQUE A"),
            (V2, L3, "ausente", "BLOQUE B"),
        ]
        for vid, lid, voto, bloque in votos:
            await s.execute(
                text(
                    "INSERT INTO voto (votacion_id, legislador_id, voto, bloque, distrito) "
                    "VALUES (:v, :l, :x, :b, 'TEST')"
                ),
                {"v": vid, "l": lid, "x": voto, "b": bloque},
            )
        await s.execute(
            text(
                "INSERT INTO reunion_comision (id, camara, external_id, fecha_hora, comision, "
                "expedientes) VALUES (:i, 'S', 'tc-reu', :f, 'DE PRUEBA', CAST(:x AS varchar[]))"
            ),
            {"i": REU, "f": datetime.now(timezone.utc) + timedelta(days=400), "x": [EXP]},
        )


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", VIGIA_TEST_DB)
    from vigia_api.core import db
    from vigia_api.main import create_app
    from vigia_shared.db import session_scope

    # El engine de la API es un singleton atado al primer event loop; cada test
    # de pytest-asyncio corre en uno nuevo.
    db._engine = db._sessionmaker = None
    await _seed()
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c
    if db._engine is not None:
        await db._engine.dispose()
    db._engine = db._sessionmaker = None
    async with session_scope() as s:
        await _limpiar(s)


async def test_filtrar_votaciones_por_expediente_en_otra_forma(client):
    r = await client.get("/congreso/votaciones", params={"expediente": "OV-9999/2099"})
    assert r.status_code == 200
    assert [v["id"] for v in r.json()["items"]] == [V1]


async def test_detalle_de_votacion(client):
    d = (await client.get(f"/congreso/votaciones/{V1}")).json()
    assert [p["id"] for p in d["proyectos"]] == [NORMA]
    assert d["sesion"]["id"] == SES
    assert d["por_bloque"][0] == {
        "bloque": "BLOQUE A", "afirmativo": 2, "negativo": 0, "abstencion": 0,
        "ausente": 0, "otro": 0, "total": 2,
    }
    assert [v["legislador_id"] for v in d["votos"]] == [L1, L2, L3]
    assert d["fecha"].endswith("-03:00")


async def test_estadisticas_del_legislador(client):
    d = (await client.get(f"/congreso/legisladores/{L1}")).json()
    # V2 no cuenta para el alineamiento: su bloque empató.
    assert d["estadisticas"] == {
        "votaciones": 2, "presentes": 2, "presentismo": 1.0, "alineamiento_bloque": 1.0,
    }
    assert [v["votacion_id"] for v in d["votos_recientes"]] == [V2, V1]

    d3 = (await client.get(f"/congreso/legisladores/{L3}")).json()
    # Monobloque: no hay con quién alinearse.
    assert d3["estadisticas"] == {
        "votaciones": 2, "presentes": 1, "presentismo": 0.5, "alineamiento_bloque": None,
    }


async def test_sesion_con_sus_votaciones(client):
    d = (await client.get(f"/congreso/sesiones/{SES}")).json()
    assert [v["id"] for v in d["votaciones"]] == [V1, V2]
    assert d["asuntos"] == []


async def test_agenda_trae_el_proyecto_cruzado(client):
    hasta = (datetime.now(timezone.utc) + timedelta(days=401)).date().isoformat()
    desde = (datetime.now(timezone.utc) + timedelta(days=399)).date().isoformat()
    d = (await client.get("/congreso/agenda", params={"desde": desde, "hasta": hasta})).json()
    (item,) = [i for i in d["items"] if i["id"] == REU]
    assert [p["id"] for p in item["proyectos"]] == [NORMA]


async def test_norma_suma_el_bloque_congreso(client):
    d = (await client.get(f"/normas/{NORMA}")).json()
    c = d["congreso"]
    assert [v["id"] for v in c["votaciones"]] == [V1]
    assert [r["id"] for r in c["reuniones"]] == [REU]
    assert c["asuntos"] == []


async def test_inexistente_da_404(client):
    for ruta in ("votaciones", "sesiones", "legisladores"):
        r = await client.get(f"/congreso/{ruta}/{BASE + 99}")
        assert r.status_code == 404
        assert r.json() == {"detail": "no_encontrado"}
