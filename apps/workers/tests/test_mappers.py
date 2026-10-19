"""Shape-tests de los mappers de ingesta.

Garantizan que cada `_to_row()` produce exactamente las columnas que
`upsert_normas` espera (las de `_NORMA_UPDATE_COLS` + external_id). Si un
conector nuevo agrega un mapper, su test de shape va acá: una key de más
rompe el INSERT; una de menos deja columnas viejas sin refrescar.
"""
from __future__ import annotations

from datetime import date

from vigia_connectors import BoraAviso, ComunicacionBcra, HcdnProyecto, InfoLegNorm, SenadoProyecto
from vigia_workers.persistence import _NORMA_UPDATE_COLS
from vigia_workers.tasks import (
    _aviso_to_row,
    _comunicacion_to_row,
    _norma_to_row,
    _proyecto_to_row,
    _senado_to_row,
)

EXPECTED_KEYS = set(_NORMA_UPDATE_COLS) | {"external_id"}
# Los mappers de proyectos suman `expedientes` (llave del cruce con el Congreso).
# `upsert_normas` la actualiza solo si el batch la trae, así que las demás
# fuentes no la mandan y no pisan lo que llenó el backfill.
EXPECTED_PROYECTO_KEYS = EXPECTED_KEYS | {"expedientes"}


def test_senado_to_row_shape():
    p = SenadoProyecto(
        numero="1040", anio="26", tipo_codigo="PL", origen="S",
        extracto="VALENZUELA: PROYECTO DE LEY QUE DECLARA FIESTA NACIONAL…",
        fecha=date(2026, 6, 12), autores=["Valenzuela Mercedes Gabriela"],
    )
    row = _senado_to_row(p)
    assert set(row.keys()) == EXPECTED_PROYECTO_KEYS
    assert row["expedientes"] == ["1040-S-2026"]
    assert row["tipo"] == "PROYECTO"
    assert row["external_id"] == "1040/26-S-PL"
    assert row["numero"] == "1040/26"
    assert row["organismo"] == "Honorable Senado de la Nación"
    assert row["fecha_publicacion"] == date(2026, 6, 12)
    assert row["entidades"] == ["Valenzuela Mercedes Gabriela"]
    assert row["tags"] == ["ley"]


def test_norma_to_row_shape():
    n = InfoLegNorm(
        id_norma="1",
        tipo_norma="Decreto",
        numero_norma="404",
        clase_norma="DNU",
        organismo_origen="PEN",
        fecha_sancion=date(2026, 5, 28),
        numero_boletin="35900",
        fecha_boletin=date(2026, 5, 29),
        pagina_boletin="1",
        titulo_resumido="ESTRUCTURA",
        titulo_sumario=None,
        texto_resumido=None,
        texto_original_url=None,
    )
    row = _norma_to_row(n)
    assert set(row.keys()) == EXPECTED_KEYS
    assert row["tipo"] == "DNU"  # clase_norma manda
    assert row["fecha_publicacion"] == date(2026, 5, 29)  # boletín > sanción
    assert row["estado"] == "Publicada"
    assert row["raw"]["fecha_boletin"] == "2026-05-29"  # dates serializadas


def test_proyecto_to_row_shape():
    p = HcdnProyecto(
        proyecto_id="2561-D-2026",
        titulo="T",
        fecha_publicacion=date(2026, 6, 2),
        camara_origen="Diputados",
        exp_diputados="2561-D-2026",
        exp_senado=None,
        tipo_proyecto="LEY",
        autor="PEREZ, Juan",
    )
    row = _proyecto_to_row(p)
    assert set(row.keys()) == EXPECTED_PROYECTO_KEYS
    assert row["expedientes"] == ["2561-D-2026"]
    assert row["tipo"] == "PROYECTO"
    assert row["numero"] == "2561-D-2026"
    assert row["estado"] == "En trámite"
    assert row["tags"] == ["ley"]


def test_proyecto_con_expediente_en_cada_camara():
    # Un proyecto del Ejecutivo que entró por Diputados y pasó al Senado: los
    # dos expedientes van al array, así cruza con votaciones de ambas cámaras.
    p = HcdnProyecto(
        proyecto_id="HCDN300000", titulo="T", fecha_publicacion=date(2026, 3, 1),
        camara_origen="Diputados", exp_diputados="0010-PE-2026", exp_senado="CD-12/26",
        tipo_proyecto="LEY", autor=None,
    )
    assert _proyecto_to_row(p)["expedientes"] == ["0010-PE-2026", "0012-CD-2026"]


def test_aviso_to_row_shape():
    a = BoraAviso(
        aviso_id="342946",
        seccion="primera",
        fecha=date(2026, 6, 10),
        organismo="MINISTERIO DE SEGURIDAD NACIONAL",
        tipo_linea="Decreto 436/2026",
        sumario="DECTO-2026-436-APN-PTE - Desígnase Subsecretario.",
    )
    row = _aviso_to_row(a)
    assert set(row.keys()) == EXPECTED_KEYS
    assert row["tipo"] == "DECRETO"
    assert row["numero"] == "436/2026"
    assert row["bora_seccion"] == "Primera Sección"
    assert row["url"].endswith("/342946/20260610")
    assert row["raw"]["tipo_linea"] == "Decreto 436/2026"  # lo usa el reconcile
    assert row["raw"]["fecha"] == "2026-06-10"

    # Promoción a DNU por texto del detalle (override del tipo).
    row_dnu = _aviso_to_row(a, tipo="DNU")
    assert row_dnu["tipo"] == "DNU"


def test_aviso_sin_sumario_usa_texto_del_detalle():
    # Rubro "Avisos Oficiales": el listado solo trae el literal "Aviso Oficial"
    # — sin el texto del detalle, el feed mostraba títulos vacíos de contenido.
    a = BoraAviso(
        aviso_id="342984",
        seccion="primera",
        fecha=date(2026, 6, 10),
        organismo="TRIBUNAL FISCAL DE LA NACIÓN",
        tipo_linea="Aviso Oficial",
        sumario="Aviso Oficial",  # genérico == tipo_linea
    )
    texto = (
        "El Tribunal Fiscal de la Nación, Sala G, comunica por dos (2) días que, "
        "en los autos: ALPEMAR S.R.L. c/ Dirección General de Aduanas s/ Recurso "
        "de Apelación, Expte. N° 35.256-A, se ha dictado la sentencia."
    )
    row = _aviso_to_row(a, texto=texto)
    assert row["titulo"].startswith("El Tribunal Fiscal de la Nación")
    assert len(row["titulo"]) <= 140
    assert "ALPEMAR" in row["resumen"]
    # Sin texto, cae al fallback de siempre.
    row_sin = _aviso_to_row(a)
    assert row_sin["titulo"] == "Aviso Oficial"
    # Con sumario real, el texto NO pisa el sumario.
    a2 = BoraAviso(
        aviso_id="1", seccion="primera", fecha=date(2026, 6, 10),
        organismo="X", tipo_linea="Decreto 1/2026", sumario="DECTO-2026-1 - Sumario real.",
    )
    assert _aviso_to_row(a2, texto=texto)["titulo"] == "DECTO-2026-1 - Sumario real."


def test_comunicacion_to_row_shape():
    c = ComunicacionBcra(
        serie="A",
        numero=8445,
        fecha=date(2026, 6, 4),
        titulo="Ratio de Cobertura de Liquidez. Adecuaciones.",
        body="Texto del MULC y los encajes. " * 100,
        url="https://www.bcra.gob.ar/Pdfs/comytexord/A8445.pdf",
    )
    row = _comunicacion_to_row(c)
    assert set(row.keys()) == EXPECTED_KEYS
    assert row["tipo"] == "COMUNICACION"
    assert row["external_id"] == "A8445"
    assert row["numero"] == "A 8445"
    assert row["organismo"].startswith("Banco Central")
    assert len(row["resumen"]) <= 1500  # excerpt para FTS, no el body entero
    assert row["raw"]["numero"] == 8445  # cursor incremental lee de acá
