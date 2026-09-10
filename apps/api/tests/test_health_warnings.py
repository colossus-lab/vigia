"""El motivo de un `warn` tiene que llegar a /health/sources.

Los guards de ingesta (listado del BORA truncado en 100, 0 avisos en día hábil)
escriben `last_status='warn'` + `last_error`, pero `_stale_reasons` solo
mostraba el error cuando el status era `error` o `stale`: el aviso se guardaba
y no se veía en ningún lado. Estos tests fijan que se vea, y que hacerlo no
convierta a la fuente en `stale` — si no, la 2ª sección del BORA, que trunca
todos los días, quedaría en rojo permanente.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from vigia_api.routers.health import _stale_reasons, _warnings


class _Row:
    def __init__(self, *, last_status, last_error=None, last_run_at=None, max_fecha=None):
        self.last_status = last_status
        self.last_error = last_error
        self.last_run_at = last_run_at
        self.max_fecha = max_fecha


_AHORA = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
_HOY = _AHORA.date()
_SRC = {"cadence_hours": 24, "freshness_slo_days": 5}


def _row_sana(**kw):
    return _Row(last_run_at=_AHORA - timedelta(hours=2), max_fecha=_HOY, **kw)


def test_warn_expone_el_motivo():
    row = _row_sana(last_status="warn", last_error="listado truncado en el tope de 100 avisos")
    assert _warnings(row) == ["listado truncado en el tope de 100 avisos"]


def test_warn_no_marca_la_fuente_como_stale():
    row = _row_sana(last_status="warn", last_error="listado truncado en el tope de 100 avisos")
    assert _stale_reasons(_SRC, row, _AHORA, _HOY) == []


def test_ok_no_tiene_warnings():
    assert _warnings(_row_sana(last_status="ok")) == []
    # warn sin mensaje no inventa un motivo vacío.
    assert _warnings(_row_sana(last_status="warn", last_error="")) == []


def test_error_sigue_siendo_stale_y_no_warning():
    row = _row_sana(last_status="error", last_error="boom")
    assert _warnings(row) == []
    assert _stale_reasons(_SRC, row, _AHORA, _HOY) == ["boom"]


def test_warn_no_tapa_un_estancamiento_real():
    """Una fuente en warn que además dejó de avanzar sigue reportando stale."""
    row = _Row(
        last_status="warn",
        last_error="listado truncado",
        last_run_at=_AHORA - timedelta(hours=2),
        max_fecha=date(2026, 8, 1),
    )
    assert _warnings(row) == ["listado truncado"]
    razones = _stale_reasons(_SRC, row, _AHORA, _HOY)
    assert len(razones) == 1 and "SLO" in razones[0]
