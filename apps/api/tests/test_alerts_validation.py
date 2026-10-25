"""Validación de criterio de alertas (funciones puras, sin DB).

Cubre el cambio que habilita alertas por-sector y por-emisor (sin keyword): una
alerta es válida con keywords O sectores O emisores; solo es inválida si los tres
están vacíos.
"""
import pytest
from fastapi import HTTPException

from vigia_api.routers.alerts import (
    _clean_emisores,
    _clean_keywords,
    _clean_sectores,
    _require_criterio,
)


def test_clean_keywords_normaliza_sin_exigir():
    # strip, sin vacías, sin duplicados, preservando orden — y NO exige ≥1.
    assert _clean_keywords([" litio ", "litio", "", "  ", "CNV"]) == ["litio", "CNV"]
    assert _clean_keywords([]) == []  # antes tiraba 422; ahora devuelve vacío


def test_require_criterio_ambos_vacios_es_422():
    with pytest.raises(HTTPException) as exc:
        _require_criterio([], [])
    assert exc.value.status_code == 422
    assert exc.value.detail == "criterio_vacio"


def test_require_criterio_ok_con_keywords_o_sectores():
    _require_criterio(["litio"], [])          # solo keywords
    _require_criterio([], ["Energía"])        # solo sectores (alerta por-sector)
    _require_criterio(["litio"], ["Energía"])  # ambos


def test_clean_sectores_valida_catalogo_y_dedup():
    assert _clean_sectores(["Energía", "Energía"]) == ["Energía"]
    assert _clean_sectores([]) == []
    with pytest.raises(HTTPException) as exc:
        _clean_sectores(["NoExiste"])
    assert exc.value.status_code == 422
    assert "sector_invalido" in exc.value.detail


def test_clean_emisores_valida_catalogo_y_dedup():
    assert _clean_emisores(["CNDC", "CNDC", "BCRA"]) == ["CNDC", "BCRA"]
    assert _clean_emisores([]) == []
    with pytest.raises(HTTPException) as exc:
        _clean_emisores(["Secretaría de Comercio"])  # texto libre: no es una clave
    assert exc.value.status_code == 422
    assert "emisor_invalido" in exc.value.detail


def test_require_criterio_alerta_solo_por_emisor():
    # Alerta por autoridad: "todo lo de la CNDC", sin keywords ni sectores.
    _require_criterio([], [], ["CNDC"])
    with pytest.raises(HTTPException) as exc:
        _require_criterio([], [], [])
    assert exc.value.detail == "criterio_vacio"
