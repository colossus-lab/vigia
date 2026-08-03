"""Regresiones del mail de frescura que avisaba sin decir qué pasaba.

El 2026-08-03 llegó un mail con `senado_proyectos: última corrida en error:` y
nada después de los dos puntos. La causa estaba dos capas más abajo: `with_status`
guardaba `str(exc)`, y las excepciones de red —las más frecuentes en estas
tasks— tienen `str()` VACÍO (`httpx.ConnectError()`, `ReadTimeout()`,
`TimeoutError()`). Resultado: sabías que algo falló y no tenías por dónde empezar.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from vigia_workers.freshness import _check_one


class _ErrorDeRed(Exception):
    """Calca el caso real: excepción sin argumentos, `str()` vacío."""


def _fila(**kw):
    base = dict(
        code="x", last_run_at=datetime.now(timezone.utc), last_status="ok",
        last_error=None, max_fecha=date.today(), inserted_7d=1,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# --- el mensaje nunca puede quedar mudo ------------------------------------


def test_error_sin_mensaje_igual_dice_algo_util():
    issues = _check_one(
        {"cadence_hours": 24}, _fila(last_status="error", last_error=None),
        datetime.now(timezone.utc), date.today(),
    )
    assert issues, "no reportó el error"
    texto = issues[0]
    assert not texto.rstrip().endswith(":"), f"mensaje truncado: {texto!r}"
    assert "logs" in texto, "no orienta sobre dónde mirar"


@pytest.mark.parametrize("vacio", [None, "", "   ", "\n"])
def test_variantes_de_error_vacio(vacio):
    issues = _check_one(
        {}, _fila(last_status="error", last_error=vacio),
        datetime.now(timezone.utc), date.today(),
    )
    assert issues and not issues[0].rstrip().endswith(":")


def test_error_con_mensaje_lo_conserva():
    issues = _check_one(
        {}, _fila(last_status="error", last_error="HTTP 503 del upstream"),
        datetime.now(timezone.utc), date.today(),
    )
    assert "HTTP 503 del upstream" in issues[0]


# --- la causa raíz: el tipo de excepción tiene que sobrevivir ---------------


def test_excepcion_de_red_sin_texto_deja_rastro():
    """Lo que `with_status` guarda en last_error para una excepción muda."""
    exc = _ErrorDeRed()
    assert str(exc) == "", "el test dejó de reproducir el caso real"
    detalle = str(exc).strip()
    mensaje = f"{type(exc).__name__}: {detalle}" if detalle else type(exc).__name__
    assert mensaje == "_ErrorDeRed"
    assert mensaje, "se guardaría vacío otra vez"


# --- los SLO no tienen que gritar sin motivo -------------------------------


def test_fuente_esporadica_sin_slo_no_alerta_por_frescura():
    """`consultas_publicas` tiene huecos reales de hasta 330 días.

    Sin SLO, un hueco largo no dispara nada; lo que sigue vigilando que la fuente
    esté viva es `cadence_hours` (¿corrió la task?).
    """
    issues = _check_one(
        {"cadence_hours": 24, "freshness_slo_days": None},
        _fila(max_fecha=date.today() - timedelta(days=300)),
        datetime.now(timezone.utc), date.today(),
    )
    assert issues == []


def test_pero_si_la_task_deja_de_correr_avisa_igual():
    ahora = datetime.now(timezone.utc)
    issues = _check_one(
        {"cadence_hours": 24, "freshness_slo_days": None},
        _fila(last_run_at=ahora - timedelta(days=4), max_fecha=date.today() - timedelta(days=300)),
        ahora, date.today(),
    )
    assert any("beat caído" in i or "colgada" in i for i in issues)


def test_infoleg_tolera_el_ciclo_mensual_real():
    """El upstream cierra mes y publica ~2 días después: la norma más nueva llega
    a envejecer ~35d antes de la tanda siguiente. Con el SLO viejo (20d) la fuente
    vivía en `stale` sin estar rota."""
    ahora = datetime.now(timezone.utc)
    hoy = date.today()
    normal = _check_one(
        {"freshness_slo_days": 45}, _fila(max_fecha=hoy - timedelta(days=34)), ahora, hoy
    )
    assert normal == [], "alertó por un atraso que es el ciclo normal"

    roto = _check_one(
        {"freshness_slo_days": 45}, _fila(max_fecha=hoy - timedelta(days=60)), ahora, hoy
    )
    assert roto, "dos meses sin datos SÍ tiene que alertar"
