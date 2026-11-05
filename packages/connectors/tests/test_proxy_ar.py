"""La salida argentina: que la usen los hosts que la necesitan, y nadie más.

`_PROXY_AR_POR_HOST` es una excepción acotada, por host, y el caller no elige
nada. Lo que estos tests cuidan es la parte que falla en silencio si se rompe:
un worker de producción sin `VIGIA_PROXY_AR` que sale directo desde AWS, se
come 60 s de timeout por intento y deja la fuente en `error` con un
`ConnectTimeout` que no dice nada de la causa.

Ninguno sale a la red ni necesita un proxy real: se comprueba qué le pasa
`make_client` a httpx, no que el proxy funcione. Eso se verifica una vez, desde
el EC2, al darlo de alta (infra/DEPLOY.md, "Salida argentina").
"""
from __future__ import annotations

import pytest

from vigia_connectors import _http

_PROXY = "http://vigia:clave-de-prueba@10.0.0.1:8888"


def test_los_hosts_bloqueados_son_exactamente_los_medidos():
    """Si esto falla, alguien agregó o sacó un host: que sea a conciencia.

    Sumar uno acá lo manda por el VPS argentino, que es chico. Sacar uno lo
    manda directo desde AWS, donde no responde. Ninguna de las dos es un
    cambio menor, y el motivo de cada uno está en el comentario del set.
    """
    assert _http._PROXY_AR_POR_HOST == frozenset(
        {
            # Medidos 2026-11-05: BORA descarta paquetes, el CKAN resetea el TLS.
            "www.boletinoficial.gob.ar",
            "datos.hcdn.gob.ar",
        }
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://servicios.infoleg.gob.ar",
        "",  # InfoLEG arma el client con base_url vacía y URLs absolutas
        "https://www.hcdn.gob.ar",  # misma IP que datos., otro vhost: responde directo
        "https://www.senado.gob.ar",
        "https://api-restboletinoficial.buenosaires.gob.ar",
        "https://boletinoficial.gba.gob.ar",
        "https://www.bcra.gob.ar",
    ],
)
def test_los_hosts_que_andan_desde_aws_salen_directo(url, monkeypatch):
    """Con el proxy configurado, las fuentes sanas NO pasan por él.

    El VPS argentino es chico: mandarle InfoLEG entero convertiría su ancho de
    banda en el cuello de botella de la ingesta entera.
    """
    monkeypatch.setenv(_http.ENV_PROXY_AR, _PROXY)
    assert _http._proxy_para(url) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://www.boletinoficial.gob.ar",
        "https://www.boletinoficial.gob.ar/seccion/primera/20261105",
        "https://datos.hcdn.gob.ar",
        "https://DATOS.hcdn.gob.ar/api/3/action/package_show?id=dictamenes",
    ],
)
def test_los_hosts_bloqueados_salen_por_el_proxy(url, monkeypatch):
    monkeypatch.setenv(_http.ENV_PROXY_AR, _PROXY)
    assert _http._proxy_para(url) == _PROXY


def test_sin_variable_el_host_bloqueado_revienta_antes_del_primer_request(monkeypatch):
    """La regresión que este módulo existe para evitar.

    El mensaje tiene que decir qué variable falta y cómo salir del paso desde
    una máquina argentina, porque quien lo lea es alguien mirando un worker
    caído y no el código.
    """
    monkeypatch.delenv(_http.ENV_PROXY_AR, raising=False)
    with pytest.raises(_http.ProxyArNoConfigurado) as exc:
        _http.make_client(base_url="https://www.boletinoficial.gob.ar")
    mensaje = str(exc.value)
    assert _http.ENV_PROXY_AR in mensaje
    assert _http.PROXY_AR_DIRECTO in mensaje
    assert "www.boletinoficial.gob.ar" in mensaje


def test_sin_variable_los_hosts_sanos_siguen_andando(monkeypatch):
    """Que el fail-fast no sea un fail-everything: InfoLEG sin la variable
    construye el client igual, porque no la necesita."""
    monkeypatch.delenv(_http.ENV_PROXY_AR, raising=False)
    client = _http.make_client(base_url="https://servicios.infoleg.gob.ar")
    assert client is not None


@pytest.mark.parametrize("valor", ["direct", "DIRECT", "  direct  "])
def test_direct_es_salir_sin_proxy(valor, monkeypatch):
    """Para dev local y para una ingesta a mano desde Argentina."""
    monkeypatch.setenv(_http.ENV_PROXY_AR, valor)
    assert _http._proxy_para("https://www.boletinoficial.gob.ar") is None


async def test_make_client_le_pasa_el_proxy_a_httpx(monkeypatch):
    """Lo que de verdad importa: el transporte del client apunta al proxy.

    Con `proxy=`, httpx monta un único transporte `all://` cuyo pool es un
    `AsyncHTTPProxy` apuntando al VPS; sin proxy no monta nada. Se verifica
    eso, sin abrir conexión alguna.
    """
    monkeypatch.setenv(_http.ENV_PROXY_AR, _PROXY)
    async with _http.make_client(base_url="https://datos.hcdn.gob.ar") as client:
        pools = [transporte._pool for transporte in client._mounts.values()]
        assert len(pools) == 1
        assert type(pools[0]).__name__ == "AsyncHTTPProxy"
        assert "10.0.0.1" in str(pools[0]._proxy_url)
    async with _http.make_client(base_url="https://servicios.infoleg.gob.ar") as directo:
        assert not directo._mounts
