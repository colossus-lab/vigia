"""Regresiones de los hallazgos #1 (secreto débil) y #8 (docs públicos).

Los tres cerrojos que se prueban acá se ven triviales en el diff y son fáciles de
revertir sin querer al tocar settings o main. De ahí el test.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from vigia_api.core.settings import Settings
from vigia_api.main import create_app

from conftest import paths_de


# --- #1: el arranque aborta con un secreto que no sirve ---------------------


@pytest.mark.parametrize(
    "secreto",
    [
        "",                      # vacío: habilitaba compare_digest("", "") -> True
        "dev-only-change-me",    # el default, público en el repo
        "change-me",
        "corto",                 # < 32 chars
        "a" * 31,                # justo por debajo del mínimo
    ],
)
def test_secreto_debil_aborta_el_arranque_con_auth_prendida(secreto):
    # `_env_file=None` hace el test hermético: sin esto lee el .env del
    # desarrollador y el resultado depende de una máquina en particular.
    with pytest.raises(ValidationError):
        Settings(_env_file=None, auth_enabled=True, auth_secret=secreto)


def test_secreto_fuerte_arranca():
    s = Settings(_env_file=None, auth_enabled=True, auth_secret="b" * 64)
    assert s.auth_enabled is True


@pytest.mark.parametrize("secreto", ["", "dev-only-change-me", "a" * 64])
def test_sin_auth_no_se_exige_secreto(secreto):
    # El modo demo (AUTH_ENABLED=false) no debe romperse: con auth apagada el
    # secreto no gatea nada, y exigirlo obligaría a configurar el entorno local.
    s = Settings(_env_file=None, auth_enabled=False, auth_secret=secreto)
    assert s.auth_enabled is False


# --- #8: docs cerrados salvo opt-in explícito -------------------------------


def _rutas(app) -> set[str]:
    return paths_de(app)


def test_docs_cerrados_por_defecto(monkeypatch):
    monkeypatch.delenv("VIGIA_DOCS", raising=False)
    app = create_app()
    assert app.openapi_url is None
    for ruta in ("/docs", "/redoc", "/openapi.json"):
        assert ruta not in _rutas(app), f"{ruta} quedó registrada"
    client = TestClient(app)
    for ruta in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(ruta).status_code == 404


def test_docs_se_pueden_prender_para_dev(monkeypatch):
    monkeypatch.setenv("VIGIA_DOCS", "true")
    app = create_app()
    assert app.openapi_url == "/openapi.json"
    assert TestClient(app).get("/openapi.json").status_code == 200


# --- #1 (segundo cerrojo): token vacío rechazado ----------------------------


def test_bearer_vacio_no_pasa_la_validacion_interna():
    from fastapi import HTTPException

    from vigia_api.routers.auth import _require_internal_secret

    # El escenario del hallazgo: secreto vacío + Bearer pelado.
    flojo = Settings(_env_file=None, auth_enabled=False, auth_secret="")
    for header in ("Bearer ", "Bearer", "Bearer   "):
        with pytest.raises(HTTPException) as exc:
            _require_internal_secret(header, flojo)
        assert exc.value.status_code in (401, 403)
