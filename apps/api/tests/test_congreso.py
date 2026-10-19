"""API `/congreso` (contrato: docs/congreso-api.md).

Sin base: rutas, que ningún modelo exponga forma interna, el Cache-Control y
las cuentas puras (desglose por bloque, presentismo, alineamiento). Lo que
necesita Postgres está en `test_congreso_db.py`.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from vigia_api import main
from vigia_api.main import create_app
from vigia_api.routers import congreso as c

from conftest import paths_de, rutas_de

RUTAS = {
    "/congreso/resumen",
    "/congreso/agenda",
    "/congreso/votaciones",
    "/congreso/votaciones/{votacion_id}",
    "/congreso/sesiones",
    "/congreso/sesiones/{sesion_id}",
    "/congreso/legisladores",
    "/congreso/legisladores/{legislador_id}",
    "/congreso/actividad",
}


def test_rutas_registradas():
    assert RUTAS <= paths_de(create_app())


def test_congreso_va_antes_que_v1():
    # `/v1` va último a propósito (main.py): no puede pisar prefijos internos.
    paths = [r.path for r in rutas_de(create_app())]
    assert paths.index("/congreso/resumen") < max(
        i for i, p in enumerate(paths) if p.startswith("/v1")
    )


def _modelos() -> list[type[BaseModel]]:
    return [
        v for v in vars(c).values()
        if isinstance(v, type) and issubclass(v, BaseModel) and v.__module__ == c.__name__
    ]


def test_ningun_modelo_expone_forma_interna():
    modelos = _modelos()
    assert len(modelos) > 10  # que el filtro no quede vacío y el test pase en falso
    for m in modelos:
        assert not set(m.model_fields) & {"raw", "search_vector"}, m.__name__


def test_congreso_es_cacheable_y_v1_no():
    assert "/congreso" in main._CACHEABLE_PREFIXES
    assert not any("/v1".startswith(p) for p in main._CACHEABLE_PREFIXES)


def test_v1_sale_sin_cache_control():
    # Con un 400 alcanza (no necesita base); el middleware solo cachea 200, así
    # que además se chequea la condición en sí arriba.
    r = TestClient(create_app()).get("/v1/normas", params={"cursor": "x"})
    assert "cache-control" not in {k.lower() for k in r.headers}


@pytest.mark.parametrize("camara", ["X", "s", "SD"])
def test_camara_invalida_da_422(camara):
    r = TestClient(create_app()).get("/congreso/votaciones", params={"camara": camara})
    assert r.status_code == 422


def test_limite_de_legisladores_llega_a_300_y_no_mas():
    client = TestClient(create_app())
    assert client.get("/congreso/legisladores", params={"limit": 301}).status_code == 422
    assert client.get("/congreso/votaciones", params={"limit": 101}).status_code == 422


# ── desglose por bloque ──────────────────────────────────────────────────────


def test_desglose_cuenta_por_bloque_y_ordena_por_total():
    filas = c.desglose_por_bloque(
        [
            ("UCR", "afirmativo"),
            ("PJ", "negativo"),
            ("PJ", "negativo"),
            ("PJ", "ausente"),
            ("UCR", "abstencion"),
            ("LLA", "afirmativo"),
        ]
    )
    assert [f["bloque"] for f in filas] == ["PJ", "UCR", "LLA"]
    pj = filas[0]
    assert pj == {
        "bloque": "PJ", "afirmativo": 0, "negativo": 2, "abstencion": 0,
        "ausente": 1, "otro": 0, "total": 3,
    }


def test_desglose_presidente_y_celda_vacia_van_a_otro():
    (f,) = c.desglose_por_bloque([("PRO", "presidente"), ("PRO", "otro"), ("PRO", "afirmativo")])
    assert f["otro"] == 2 and f["afirmativo"] == 1 and f["total"] == 3


def test_desglose_empate_de_totales_desempata_por_nombre_y_sin_bloque_al_final():
    filas = c.desglose_por_bloque([("B", "afirmativo"), (None, "negativo"), ("A", "afirmativo")])
    assert [f["bloque"] for f in filas] == ["A", "B", None]


def test_desglose_bloque_de_un_solo_legislador():
    (f,) = c.desglose_por_bloque([("MONOBLOQUE", "negativo")])
    assert f["total"] == 1 and f["negativo"] == 1


def test_desglose_votacion_sin_votos():
    assert c.desglose_por_bloque([]) == []


# ── presentismo ──────────────────────────────────────────────────────────────


def test_presentismo():
    assert c.presentismo(140, 9) == (131, 0.936)
    assert c.presentismo(10, 0) == (10, 1.0)
    assert c.presentismo(4, 4) == (0, 0.0)


def test_presentismo_sin_votaciones_es_none_no_cero():
    assert c.presentismo(0, 0) == (0, None)


# ── alineamiento ─────────────────────────────────────────────────────────────


def test_alineamiento_basico():
    filas = [
        ("afirmativo", 10, 2),   # alineado
        ("negativo", 10, 2),     # en contra de su bloque
        ("negativo", 1, 9),      # alineado
        ("afirmativo", 8, 0),    # alineado
    ]
    assert c.alineamiento_bloque(filas) == 0.75


def test_alineamiento_descarta_empates_del_bloque():
    assert c.alineamiento_bloque([("afirmativo", 3, 3)]) is None
    assert c.alineamiento_bloque([("afirmativo", 3, 3), ("afirmativo", 4, 1)]) == 1.0


def test_alineamiento_monobloque_no_cuenta():
    # Solo él votó sí/no en su bloque: alinearse con uno mismo no dice nada.
    assert c.alineamiento_bloque([("negativo", 0, 1), ("afirmativo", 1, 0)]) is None


def test_alineamiento_ignora_votos_que_no_son_si_o_no():
    assert c.alineamiento_bloque([("abstencion", 5, 1), ("ausente", 5, 1)]) is None


def test_alineamiento_sin_votaciones():
    assert c.alineamiento_bloque([]) is None


# ── otros helpers ────────────────────────────────────────────────────────────


def test_detalle_votacion():
    assert c.detalle_votacion("afirmativo", 42, 30) == "afirmativo 42-30"
    assert c.detalle_votacion(None, 42, 30) == "42-30"
    assert c.detalle_votacion("negativo", None, None) == "negativo"
    assert c.detalle_votacion(None, None, None) is None


def _p(i: int) -> c.ProyectoRef:
    return c.ProyectoRef(id=i, titulo=f"P{i}", numero=None, estado=None, fecha_publicacion=None)


def test_asignar_proyectos_reparte_por_solapamiento():
    proyectos = [(_p(1), ["0010-PE-2026", "0012-CD-2026"]), (_p(2), ["0005-S-2026"])]
    out = c.asignar_proyectos([["0012-CD-2026"], [], ["0005-S-2026", "0010-PE-2026"]], proyectos)
    assert [[p.id for p in ps] for ps in out] == [[1], [], [1, 2]]


def test_asignar_proyectos_respeta_el_tope_por_item():
    proyectos = [(_p(i), ["0001-S-2026"]) for i in range(25)]
    (out,) = c.asignar_proyectos([["0001-S-2026"]], proyectos)
    assert len(out) == c._MAX_PROYECTOS


def test_fechas_con_offset_argentino():
    from datetime import datetime, timezone

    dt = c._art(datetime(2026, 2, 11, 5, 29, tzinfo=timezone.utc))
    assert dt.isoformat() == "2026-02-11T02:29:00-03:00"
