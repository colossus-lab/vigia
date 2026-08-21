"""Aritmética de créditos (funciones puras, sin DB).

Lo que más importa acá no es la conversión de unidades sino los invariantes que
sostienen el resto del sistema: que el período se calcule igual en las dos
puntas (la que lee el saldo y la que cobra), que un aporte vencido o corrupto
falle cerrado, y que la promesa que hace /apoyar siga siendo cierta.
"""
from datetime import date

import pytest

from vigia_shared import creditos as cred


# --------------------------------------------------------------------------- #
# Plata ↔ créditos
# --------------------------------------------------------------------------- #

def test_un_digest_es_un_credito():
    # La equivalencia que hace que el medidor se pueda explicar en una línea.
    assert cred.creditos_de(cred.micros_de("digest")) == 1.0


def test_accion_desconocida_no_cobra():
    # Un tipo de consumo nuevo mal escrito no puede cobrar de más ni romper la
    # ingesta: sale 0 y se nota en el contador, no en la cara del usuario.
    assert cred.micros_de("todavia_no_existe") == 0


def test_micros_de_no_acepta_cantidad_negativa():
    assert cred.micros_de("digest", -5) == 0


def test_creditos_de_redondea_a_un_decimal():
    assert cred.creditos_de(15_000) == 1.5
    assert cred.creditos_de(None) == 0.0
    assert cred.creditos_de(0) == 0.0


# --------------------------------------------------------------------------- #
# Período — el invariante del que depende que el saldo no mienta
# --------------------------------------------------------------------------- #

def test_free_y_pleno_cuentan_por_mes():
    assert cred.periodo_de("free", None, date(2026, 8, 5)) == "2026-08"
    assert cred.periodo_de("pleno", None, date(2026, 8, 20)) == "2026-08"


def test_base_parte_el_mes_en_el_dia_16():
    assert cred.periodo_de("base", None, date(2026, 8, 15)) == "2026-08q1"
    assert cred.periodo_de("base", None, date(2026, 8, 16)) == "2026-08q2"


def test_el_periodo_cambia_al_activar_el_aporte():
    # Pasar a `base` a mitad de mes tiene que arrancar en cero, y eso sale gratis
    # justamente porque cambia la clave: no hay lógica de prorrateo en ningún lado.
    hoy = date(2026, 8, 20)
    assert cred.periodo_de("free", None, hoy) != cred.periodo_de("base", None, hoy)


def test_renueva_el_primer_dia_del_mes_que_viene():
    assert cred.renueva_el("free", None, date(2026, 12, 20)) == date(2027, 1, 1)
    # Febrero: el cálculo parte del día 28, así que no se pasa de mes.
    assert cred.renueva_el("free", None, date(2027, 2, 15)) == date(2027, 3, 1)


def test_base_renueva_en_la_quincena():
    assert cred.renueva_el("base", None, date(2026, 8, 5)) == date(2026, 8, 16)
    assert cred.renueva_el("base", None, date(2026, 8, 20)) == date(2026, 9, 1)


# --------------------------------------------------------------------------- #
# Nivel de aporte
# --------------------------------------------------------------------------- #

def test_sin_aporte_no_hay_nivel():
    assert cred.nivel_de("free", None) is None
    assert cred.nivel_de(None, None) is None


def test_aporte_sin_hasta_no_vence():
    assert cred.nivel_de("pleno", {"desde": "2026-01-01"}, date(2030, 1, 1)) == "pleno"


def test_aporte_vencido_deja_de_valer():
    marca = {"hasta": "2026-08-20"}
    assert cred.nivel_de("pleno", marca, date(2026, 8, 20)) == "pleno"  # el último día vale
    assert cred.nivel_de("pleno", marca, date(2026, 8, 21)) is None


def test_fecha_corrupta_falla_cerrado():
    # Un `hasta` ilegible no puede convertirse en barra libre.
    assert cred.nivel_de("pleno", {"hasta": "ayer"}, date(2026, 8, 21)) is None


def test_plan_desconocido_no_da_nivel():
    assert cred.nivel_de("enterprise", None) is None


# --------------------------------------------------------------------------- #
# Estado
# --------------------------------------------------------------------------- #

def test_disponibles_none_solo_en_pleno():
    # None ("sin cupo") y 0 ("se acabó") son estados distintos y el front los
    # discrimina por esto: colapsarlos rompería la barra y el cartel.
    assert cred.estado(0, "free")["disponibles"] == float(cred.CUPO_POR_DEFECTO)
    assert cred.estado(10**9, "pleno")["disponibles"] is None


def test_pleno_nunca_se_agota():
    assert cred.estado(10**9, "pleno")["agotados"] is False


def test_agotados_justo_en_el_limite():
    cupo_en_micros = cred.CUPO_POR_DEFECTO * cred.MICROS_POR_CREDITO
    assert cred.estado(cupo_en_micros - 1, "free")["agotados"] is False
    assert cred.estado(cupo_en_micros, "free")["agotados"] is True


def test_disponibles_no_baja_de_cero():
    # El sobregiro existe (se cobra después de mandar), pero no se muestra en rojo
    # negativo: la barra se queda en cero.
    assert cred.estado(10**9, "free")["disponibles"] == 0.0


def test_estado_trae_todo_lo_que_la_web_necesita():
    e = cred.estado(0, "base", {"desde": "2026-08-01"}, date(2026, 8, 5))
    assert set(e) == {
        "usados", "cupo", "disponibles", "agotados",
        "nivel", "quincenal", "renueva", "contacto",
    }
    assert e["quincenal"] is True
    assert e["renueva"] == "2026-08-16"


# --------------------------------------------------------------------------- #
# La promesa comercial, atada al código
# --------------------------------------------------------------------------- #

def test_el_cupo_alcanza_para_unos_tres_mails_por_dia():
    """Lo que promete /apoyar. Si esto se rompe, hay que cambiar el texto."""
    cupo = cred.CUPO_POR_DEFECTO * cred.MICROS_POR_CREDITO
    por_dia = cupo / cred.micros_de("digest") / 30
    assert 2.5 <= por_dia <= 3.5


def test_el_cupo_le_sobra_al_uso_real_medido():
    """Medido el 2026-08-21 sobre 30 días de producción: la mediana de los 110
    workspaces que reciben digests consume 18 mails al mes y el más pesado 60.
    El cupo tiene que quedar por encima de ese máximo — el techo está para el
    crecimiento, no para cobrarle a quien ya está usando la plataforma."""
    assert cred.CUPO_POR_DEFECTO > 60


@pytest.mark.parametrize("plan", ["free", "base", "pleno"])
def test_ningun_plan_rompe_estado(plan):
    e = cred.estado(12_345, plan, {"desde": "2026-01-01"})
    assert isinstance(e["usados"], float)
    assert isinstance(e["agotados"], bool)
