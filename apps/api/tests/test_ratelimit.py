"""Regresiones del hallazgo #4: no había ningún rate limiting.

Herméticos, sin base y sin red, como el resto de la suite. Ojo con dos cosas que
hacen frágiles estos tests si no se cuidan:

- El estado del limiter es de MÓDULO y se filtra entre tests → `reset()` en una
  fixture autouse.
- `TestClient` reporta siempre el mismo `request.client.host`, así que para
  distinguir IPs hay que inyectar `X-Forwarded-For`.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from vigia_api.core import ratelimit
from vigia_api.core.ratelimit import (
    consultar,
    consumir,
    limitar_por_ip,
    registrar,
    reset,
)
from vigia_api.core.settings import Settings


@pytest.fixture(autouse=True)
def _limpiar():
    reset()
    yield
    reset()


# --- la mecánica del contador ----------------------------------------------


def test_deja_pasar_hasta_la_cuota_y_despues_corta():
    for i in range(5):
        assert consumir("k", limite=5, ventana=60) is None, f"cortó en el intento {i + 1}"
    espera = consumir("k", limite=5, ventana=60)
    assert espera is not None and espera > 0


def test_las_claves_no_se_pisan():
    for _ in range(5):
        consumir("a", limite=5, ventana=60)
    # 'a' agotado, 'b' intacto: si compartieran contador esto fallaría.
    assert consumir("a", limite=5, ventana=60) is not None
    assert consumir("b", limite=5, ventana=60) is None


def test_la_ventana_se_desliza(monkeypatch):
    reloj = {"t": 1000.0}
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: reloj["t"])
    for _ in range(3):
        assert consumir("k", limite=3, ventana=10) is None
    assert consumir("k", limite=3, ventana=10) is not None
    reloj["t"] += 11          # la ventana pasó entera
    assert consumir("k", limite=3, ventana=10) is None


def test_ventana_deslizante_no_tiene_el_agujero_del_borde(monkeypatch):
    """Con ventana FIJA, 2x la cuota entra a caballo de dos ventanas. Acá no."""
    reloj = {"t": 1000.0}
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: reloj["t"])
    for _ in range(3):
        consumir("k", limite=3, ventana=10)
    reloj["t"] += 9.9          # casi vencida, pero no
    assert consumir("k", limite=3, ventana=10) is not None


def test_consultar_no_consume():
    for _ in range(5):
        assert consultar("k", limite=5, ventana=60) is None
    # cinco consultas y ni un hit registrado
    assert consumir("k", limite=5, ventana=60) is None


def test_registrar_cuenta_sin_consultar():
    for _ in range(5):
        registrar("k", ventana=60)
    assert consultar("k", limite=5, ventana=60) is not None


# --- la dependency ----------------------------------------------------------


class _Req:
    """Request mínimo: solo lo que mira `client_ip`."""

    def __init__(self, ip: str | None):
        self.headers = {"x-forwarded-for": ip} if ip else {}
        self.client = None


_PRENDIDO = Settings(_env_file=None, ratelimit_enabled=True)
_APAGADO = Settings(_env_file=None, ratelimit_enabled=False)


def test_dependency_por_ip_separa_clientes():
    dep = limitar_por_ip("prueba", limite=2, ventana=60)
    for _ in range(2):
        asyncio.run(dep(_Req("1.1.1.1"), _PRENDIDO))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(_Req("1.1.1.1"), _PRENDIDO))
    assert exc.value.status_code == 429
    assert exc.value.detail == "rate_limited"
    assert int(exc.value.headers["Retry-After"]) >= 1
    # Otra IP arranca con la cuota entera.
    asyncio.run(dep(_Req("2.2.2.2"), _PRENDIDO))


def test_se_puede_apagar_por_config():
    dep = limitar_por_ip("prueba", limite=1, ventana=60)
    for _ in range(10):
        asyncio.run(dep(_Req("1.1.1.1"), _APAGADO))  # no debe levantar nunca
    # …y prendido, el mismo escenario sí corta: el test de arriba no pasa por
    # casualidad.
    reset()
    asyncio.run(dep(_Req("1.1.1.1"), _PRENDIDO))
    with pytest.raises(HTTPException):
        asyncio.run(dep(_Req("1.1.1.1"), _PRENDIDO))


def test_sin_settings_el_limite_aplica():
    """Fail-safe: si nadie inyectó config, se limita. El default no es 'abierto'."""
    dep = limitar_por_ip("prueba", limite=1, ventana=60)
    asyncio.run(dep(_Req(None), None))
    with pytest.raises(HTTPException):
        asyncio.run(dep(_Req(None), None))


# --- client_ip: la premisa del diseño ---------------------------------------


def test_client_ip_toma_el_primer_elemento():
    """Es seguro PORQUE Caddy reemplaza el XFF (verificado contra caddy v2.11.4).

    Si algún día se pone un CDN o proxy delante de Caddy, esta premisa se rompe y
    hay que tomar el último elemento. El test documenta la decisión.
    """
    assert ratelimit.client_ip(_Req("9.9.9.9")) == "9.9.9.9"
    assert ratelimit.client_ip(_Req("9.9.9.9, 10.0.0.1")) == "9.9.9.9"
    assert ratelimit.client_ip(None) is None


# --- integración: el 429 tiene que llegar al browser con CORS ---------------


def test_auth_sync_corta_la_fuerza_bruta_y_el_429_trae_cors(monkeypatch):
    """El caso que justifica cablear el limiter como dependency y no middleware.

    Starlette apila los middlewares al revés de como se leen: un limiter
    registrado después de CORSMiddleware queda por FUERA, y sus 429 salen sin
    Access-Control-Allow-Origin — el browser vería un error de red opaco en vez
    de un 429. Como dependency, la excepción la maneja ExceptionMiddleware, que
    corre por dentro de CORS.

    Además valida que se limitan FALLOS y no intentos: /auth/sync lo llama el
    server de Next en cada login desde las IPs de Vercel.
    """
    from fastapi.testclient import TestClient

    from vigia_api.main import create_app

    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("API_CORS_ORIGINS", "https://vigia.openarg.org")
    client = TestClient(create_app())

    cuerpo = {"email": "atacante@example.com", "name": "x"}
    cabeceras = {
        "Authorization": "Bearer secreto-equivocado",
        "Origin": "https://vigia.openarg.org",
        "X-Forwarded-For": "203.0.113.7",
    }

    codigos = [
        client.post("/auth/sync", json=cuerpo, headers=cabeceras).status_code
        for _ in range(12)
    ]
    assert codigos[0] == 403, "el primer intento debería rebotar por secreto inválido"
    assert 429 in codigos, "nunca cortó: la fuerza bruta quedaría libre"
    assert codigos.index(429) == 10, f"cortó en el intento {codigos.index(429) + 1}, esperaba el 11"

    r = client.post("/auth/sync", json=cuerpo, headers=cabeceras)
    assert r.status_code == 429
    assert r.headers.get("access-control-allow-origin") == "https://vigia.openarg.org", (
        "el 429 salió sin CORS: el browser vería un error de red opaco"
    )
    assert r.headers.get("Retry-After")

    # Otra IP no arrastra el bloqueo.
    otra = dict(cabeceras, **{"X-Forwarded-For": "203.0.113.99"})
    assert client.post("/auth/sync", json=cuerpo, headers=otra).status_code == 403
