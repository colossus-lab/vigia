"""API keys: acuñado del secreto, verificación y cuota.

Lo que se cuida acá:

- que el secreto no se pueda reconstruir de lo que queda guardado,
- que `/v1` no se pueda consumir sin credencial,
- que los endpoints públicos que usa el web **no** hayan quedado gateados de
  rebote al montar la dependency en el router de `/v1`.

Herméticos: sin base y sin red. La verificación contra filas reales (key
revocada, `last_used_at`, aislamiento entre workspaces) va en el e2e con
Postgres, porque necesita una fila de verdad.
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from vigia_api.core import ratelimit
from vigia_api.core.apikeys import (
    PREFIJO,
    ApiClient,
    _extraer_token,
    generar,
    hashear,
    reset_memo_uso,
)
from vigia_api.core.ratelimit import (
    consumir_diario,
    limitar_por_apikey,
    reset,
    segundos_hasta_reset_diario,
)
from vigia_api.core.settings import Settings
from vigia_api.main import create_app


@pytest.fixture(autouse=True)
def _limpiar():
    reset()
    reset_memo_uso()
    yield
    reset()
    reset_memo_uso()


# --- acuñado del secreto ----------------------------------------------------


def test_el_secreto_lleva_el_prefijo_reconocible():
    # El prefijo fijo es lo que hace que una key filtrada se pueda detectar en
    # un repo o un log, propio o de un escáner de secretos.
    secreto, _, _ = generar()
    assert secreto.startswith(PREFIJO)


def test_lo_guardado_no_permite_reconstruir_el_secreto():
    secreto, prefijo, token_hash = generar()
    # El prefijo es un pedazo chico y el hash no es invertible: con la fila
    # entera en la mano no se puede volver al secreto.
    assert secreto.startswith(prefijo)
    assert len(prefijo) < len(secreto) / 2
    assert token_hash == hashlib.sha256(secreto.encode()).hexdigest()
    assert secreto not in token_hash


def test_dos_keys_nunca_coinciden():
    secretos = {generar()[0] for _ in range(200)}
    assert len(secretos) == 200


def test_el_hash_es_estable_y_discrimina():
    secreto, _, token_hash = generar()
    assert hashear(secreto) == token_hash
    assert hashear(secreto + "x") != token_hash


def test_entropia_suficiente():
    # 32 bytes url-safe → 43 chars. Si alguien baja el largo, esto avisa.
    secreto, _, _ = generar()
    assert len(secreto) - len(PREFIJO) >= 40


# --- lectura del header -----------------------------------------------------


@pytest.mark.parametrize(
    "header",
    [None, "", "Bearer", "Bearer ", "Bearer    ", "Basic abc", "vg_live_sinbearer"],
)
def test_headers_que_no_traen_key(header):
    with pytest.raises(HTTPException) as exc:
        _extraer_token(header)
    assert exc.value.status_code == 401
    assert exc.value.detail == "missing_api_key"
    assert "Bearer" in exc.value.headers["WWW-Authenticate"]


def test_el_jwt_de_sesion_no_pasa_por_api_key():
    # El error real: alguien copia el token del web y lo pega contra /v1. El
    # detalle tiene que mandarlo al lado correcto del problema.
    jwt_falso = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.firma"
    with pytest.raises(HTTPException) as exc:
        _extraer_token(f"Bearer {jwt_falso}")
    assert exc.value.detail == "no_es_una_api_key"


def test_el_esquema_bearer_no_distingue_mayusculas():
    secreto, _, _ = generar()
    assert _extraer_token(f"bearer {secreto}") == secreto
    assert _extraer_token(f"BEARER {secreto}") == secreto


# --- cuota diaria -----------------------------------------------------------


def test_la_cuota_diaria_se_agota_y_devuelve_el_remanente():
    restantes = []
    for _ in range(3):
        cuota = consumir_diario("k", limite=3)
        assert cuota is not None
        restantes.append(cuota[0])
    assert restantes == [2, 1, 0]
    assert consumir_diario("k", limite=3) is None


def test_el_reset_cae_dentro_del_dia():
    _, reset_en = consumir_diario("k", limite=10)
    assert 1 <= reset_en <= 86400


def test_la_cuota_diaria_se_reinicia_al_cambiar_el_dia(monkeypatch):
    class _Reloj:
        actual = datetime(2026, 8, 12, 23, 59, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            return cls.actual

    monkeypatch.setattr(ratelimit, "datetime", _Reloj)
    for _ in range(2):
        assert consumir_diario("k", limite=2) is not None
    assert consumir_diario("k", limite=2) is None

    _Reloj.actual = datetime(2026, 8, 13, 0, 1, tzinfo=timezone.utc)
    assert consumir_diario("k", limite=2) is not None, "el día cambió y la cuota no se reinició"


def test_las_claves_diarias_no_se_pisan():
    consumir_diario("a", limite=1)
    assert consumir_diario("a", limite=1) is None
    assert consumir_diario("b", limite=1) is not None


def test_segundos_hasta_reset_a_un_minuto_de_medianoche():
    casi = datetime(2026, 8, 12, 23, 59, 0, tzinfo=timezone.utc)
    assert segundos_hasta_reset_diario(casi) == 60


# --- la dependency de /v1 ---------------------------------------------------


class _Resp:
    """Response mínimo: solo el dict de headers que toca la dependency."""

    def __init__(self):
        self.headers: dict[str, str] = {}


_CLIENTE = ApiClient(workspace_id=7, api_key_id=42, name="ETL")
_DEMO = ApiClient(workspace_id=0, api_key_id=None, name="demo")


def _correr(dep, cliente, settings):
    return asyncio.run(dep(_Resp(), cliente, settings))


def test_la_cuota_va_con_headers_para_el_integrador():
    dep = limitar_por_apikey("v1")
    s = Settings(_env_file=None, ratelimit_enabled=True, apikey_rate_por_dia=10)
    resp = _Resp()
    asyncio.run(dep(resp, _CLIENTE, s))
    assert resp.headers["X-RateLimit-Limit"] == "10"
    assert resp.headers["X-RateLimit-Remaining"] == "9"
    assert int(resp.headers["X-RateLimit-Reset"]) >= 1


def test_el_remanente_baja_request_a_request():
    dep = limitar_por_apikey("v1")
    s = Settings(_env_file=None, ratelimit_enabled=True, apikey_rate_por_dia=5)
    vistos = []
    for _ in range(3):
        resp = _Resp()
        asyncio.run(dep(resp, _CLIENTE, s))
        vistos.append(resp.headers["X-RateLimit-Remaining"])
    assert vistos == ["4", "3", "2"]


def test_la_rafaga_por_minuto_corta_antes_que_la_diaria():
    dep = limitar_por_apikey("v1")
    s = Settings(
        _env_file=None, ratelimit_enabled=True, apikey_rate_por_minuto=2, apikey_rate_por_dia=1000
    )
    for _ in range(2):
        _correr(dep, _CLIENTE, s)
    with pytest.raises(HTTPException) as exc:
        _correr(dep, _CLIENTE, s)
    assert exc.value.status_code == 429
    assert exc.value.detail == "rate_limited"


def test_la_cuota_diaria_agotada_tiene_su_propio_detalle():
    # Distinto de `rate_limited`: reintentar en un minuto no lo arregla, y el
    # Retry-After tiene que llevar hasta el reset.
    dep = limitar_por_apikey("v1")
    s = Settings(
        _env_file=None, ratelimit_enabled=True, apikey_rate_por_minuto=1000, apikey_rate_por_dia=2
    )
    for _ in range(2):
        _correr(dep, _CLIENTE, s)
    with pytest.raises(HTTPException) as exc:
        _correr(dep, _CLIENTE, s)
    assert exc.value.status_code == 429
    assert exc.value.detail == "cuota_diaria_agotada"
    assert int(exc.value.headers["Retry-After"]) >= 1


def test_dos_keys_tienen_cuotas_separadas():
    dep = limitar_por_apikey("v1")
    s = Settings(_env_file=None, ratelimit_enabled=True, apikey_rate_por_dia=1)
    _correr(dep, _CLIENTE, s)
    with pytest.raises(HTTPException):
        _correr(dep, _CLIENTE, s)
    otra = ApiClient(workspace_id=7, api_key_id=99, name="otra")
    _correr(dep, otra, s)  # misma workspace, otra key: cuota propia


def test_en_modo_demo_no_se_limita_ni_se_ponen_headers():
    dep = limitar_por_apikey("v1")
    s = Settings(_env_file=None, ratelimit_enabled=True, apikey_rate_por_dia=1)
    for _ in range(5):
        resp = _Resp()
        asyncio.run(dep(resp, _DEMO, s))
        assert resp.headers == {}


def test_se_puede_apagar_por_config():
    dep = limitar_por_apikey("v1")
    s = Settings(_env_file=None, ratelimit_enabled=False, apikey_rate_por_dia=1)
    for _ in range(5):
        _correr(dep, _CLIENTE, s)


# --- superficie HTTP --------------------------------------------------------


@pytest.fixture
def app_con_auth(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_SECRET", "z" * 64)
    return create_app()


def test_v1_sin_credencial_no_pasa(app_con_auth):
    # Corta en la dependency, antes de tocar la base: si no fuera así, este test
    # explotaría por falta de Postgres en vez de responder 401.
    r = TestClient(app_con_auth).get("/v1/normas")
    assert r.status_code == 401
    assert r.json()["detail"] == "missing_api_key"
    assert "Bearer" in r.headers.get("www-authenticate", "")


def test_v1_con_un_bearer_que_no_es_key_no_llega_a_la_base(app_con_auth):
    # Un secreto inexistente sí necesita el lookup por hash (va en el e2e con
    # Postgres); uno que ni siquiera tiene el prefijo se rechaza antes.
    r = TestClient(app_con_auth).get(
        "/v1/normas", headers={"Authorization": "Bearer token-de-otra-cosa"}
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "no_es_una_api_key"


def test_el_detalle_de_v1_tambien_esta_gateado(app_con_auth):
    assert TestClient(app_con_auth).get("/v1/normas/1").status_code == 401


def _exige_api_key(route) -> bool:
    """¿La ruta tiene `current_api_client` en su árbol de dependencies?

    Se mira el árbol y no el código de respuesta porque probar por HTTP que
    `/normas` NO pide key obliga a que la request llegue hasta Postgres. Acá lo
    que importa es dónde está colgada la dependency, y eso se puede leer sin
    levantar nada.
    """
    from vigia_api.core.apikeys import current_api_client

    pendientes = [route.dependant]
    while pendientes:
        dep = pendientes.pop()
        if dep.call is current_api_client:
            return True
        pendientes.extend(dep.dependencies)
    return False


def test_todo_v1_exige_api_key(app_con_auth):
    rutas = [r for r in app_con_auth.routes if getattr(r, "path", "").startswith("/v1")]
    assert rutas, "no se registró ninguna ruta /v1"
    for r in rutas:
        assert _exige_api_key(r), f"{r.path} quedó sin credencial"


def test_los_endpoints_del_web_siguen_sin_pedir_credencial(app_con_auth):
    """La dependency va en el router de /v1: no puede haber goteado al resto."""
    publicas = ("/normas", "/normas/ediciones", "/search", "/stats/dashboard", "/avisos", "/health")
    porRuta = {getattr(r, "path", ""): r for r in app_con_auth.routes}
    for ruta in publicas:
        assert ruta in porRuta, f"{ruta} desapareció"
        assert not _exige_api_key(porRuta[ruta]), f"{ruta} quedó pidiendo API key"


def test_gestionar_keys_exige_sesion_no_api_key(app_con_auth):
    # /api-keys se autentica con la sesión: una key no puede emitir otra key.
    client = TestClient(app_con_auth)
    assert client.get("/api-keys").status_code == 401
    secreto, _, _ = generar()
    r = client.get("/api-keys", headers={"Authorization": f"Bearer {secreto}"})
    assert r.status_code == 401, "una API key no debería servir para gestionar keys"
