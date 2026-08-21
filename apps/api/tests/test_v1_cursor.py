"""Regresiones de la paginación por cursor de `/v1/normas`.

Lo que se cuida acá no es que el listado "ande": es que no se saltee filas en
silencio. Un cursor reusado entre dos órdenes distintos, o un cursor de un
formato viejo interpretado a la fuerza, devuelven una página que parece
perfectamente válida y le deja agujeros al que sincroniza. De ahí que cada uno
de esos casos tenga que terminar en 400 y no en datos.

No tocan la base: el cursor se decodifica antes de abrir sesión, así que estos
casos se pueden ejercitar con `TestClient` pelado.
"""
from __future__ import annotations

import base64
import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from vigia_api.main import create_app
from vigia_api.routers.v1 import cursor as cur

from conftest import paths_de


def _crudo(payload: dict) -> str:
    """Arma un cursor a mano para simular uno viejo, ajeno o manipulado."""
    data = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


# --- codec ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("modo", "clave", "id_"),
    [
        (cur.MODO_FEED, "2026-08-01", 123),
        (cur.MODO_FEED, None, 2**63 - 1),          # tramo de normas sin fecha
        (cur.MODO_SYNC, "2026-08-01T10:00:00+00:00", 1),
    ],
)
def test_roundtrip(modo, clave, id_):
    token = cur.encode(modo=modo, clave=clave, id_=id_)
    assert cur.decode(token, modo_esperado=modo) == (clave, id_)


def test_el_cursor_no_lleva_padding():
    # Los `=` finales obligan a url-encodear el cursor y todo el mundo se
    # olvida una vez; que no aparezcan es parte del contrato.
    for id_ in range(1, 40):
        assert "=" not in cur.encode(modo=cur.MODO_FEED, clave="2026-08-01", id_=id_)


def test_cursor_de_feed_no_sirve_para_sync():
    token = cur.encode(modo=cur.MODO_FEED, clave="2026-08-01", id_=5)
    with pytest.raises(HTTPException) as exc:
        cur.decode(token, modo_esperado=cur.MODO_SYNC)
    assert exc.value.status_code == 400
    assert exc.value.detail == "cursor_de_otro_orden"


def test_cursor_de_sync_no_sirve_para_feed():
    token = cur.encode(modo=cur.MODO_SYNC, clave="2026-08-01T00:00:00+00:00", id_=5)
    with pytest.raises(HTTPException) as exc:
        cur.decode(token, modo_esperado=cur.MODO_FEED)
    assert exc.value.detail == "cursor_de_otro_orden"


def test_version_desconocida_no_se_interpreta_igual():
    token = _crudo({"v": 99, "m": cur.MODO_FEED, "k": "2026-08-01", "i": 5})
    with pytest.raises(HTTPException) as exc:
        cur.decode(token, modo_esperado=cur.MODO_FEED)
    assert exc.value.detail == "cursor_de_version_desconocida"


@pytest.mark.parametrize(
    "token",
    [
        "no-es-base64-!!",
        base64.urlsafe_b64encode(b"esto no es json").decode().rstrip("="),
        _crudo({"v": 1, "m": "feed", "k": "2026-08-01"}),          # sin id
        _crudo({"v": 1, "m": "feed", "k": "2026-08-01", "i": "5"}),  # id string
        _crudo({"v": 1, "m": "feed", "k": 20260801, "i": 5}),       # clave no-string
        _crudo({"v": 1, "m": "feed", "k": None, "i": True}),        # bool no es id
        _crudo(["v", 1]),                                            # ni siquiera un objeto
    ],
)
def test_cursores_rotos_dan_400(token):
    with pytest.raises(HTTPException) as exc:
        cur.decode(token, modo_esperado=cur.MODO_FEED)
    assert exc.value.status_code == 400
    assert exc.value.detail == "cursor_invalido"


# --- superficie HTTP --------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_v1_esta_montado():
    rutas = paths_de(create_app())
    assert "/v1/normas" in rutas
    assert "/v1/normas/{norma_id}" in rutas


def test_los_routers_internos_siguen_donde_estaban():
    # El punto de /v1 es no tocar lo que consume el web: si esto se cae, el
    # BFF y las páginas se quedan sin backend.
    rutas = paths_de(create_app())
    for ruta in ("/normas", "/normas/{norma_id}", "/search", "/stats/dashboard"):
        assert ruta in rutas


def test_cursor_podrido_corta_antes_de_la_base(client):
    # Sin Postgres levantado: si el 400 no saliera del decode, esto explotaría
    # con un error de conexión en vez de responder.
    r = client.get("/v1/normas", params={"cursor": "chirimbolo"})
    assert r.status_code == 400
    assert r.json()["detail"] == "cursor_invalido"


def test_reusar_el_cursor_del_feed_en_una_sync_no_pasa(client):
    token = cur.encode(modo=cur.MODO_FEED, clave="2026-08-01", id_=5)
    r = client.get("/v1/normas", params={"cursor": token, "updated_since": "2026-08-01T00:00:00Z"})
    assert r.status_code == 400
    assert r.json()["detail"] == "cursor_de_otro_orden"


@pytest.mark.parametrize("limit", [0, -1, 201, 5000])
def test_limit_fuera_de_rango(client, limit):
    assert client.get("/v1/normas", params={"limit": limit}).status_code == 422


def test_updated_since_tiene_que_ser_una_fecha(client):
    assert client.get("/v1/normas", params={"updated_since": "ayer"}).status_code == 422


def test_el_contrato_publico_no_expone_el_crudo_de_las_fuentes():
    # `raw` y `search_vector` son forma interna: si se filtran al schema
    # público quedamos atados a ellos.
    from vigia_api.routers.v1.schemas import NormaPublic, NormaPublicDetail

    for schema in (NormaPublic, NormaPublicDetail):
        campos = set(schema.model_fields)
        assert not campos & {"raw", "search_vector", "source_id"}
    assert "updated_at" in NormaPublic.model_fields
