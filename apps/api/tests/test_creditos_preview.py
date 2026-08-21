"""Estimación de costo en el preview de alertas (función pura, sin DB).

`count_30d` (normas que matchean) y "cuántos mails vas a recibir" no son lo
mismo y por mucho: hasta 20 normas que caen en la misma corrida viajan en un
solo digest. Si el preview mostrara el count crudo como costo, una alerta
normal parecería impagable.
"""
from vigia_api.routers.alerts import _TECHO_MAILS_MES, _digests_estimados
from vigia_shared import creditos as cred


def test_sin_matches_no_cuesta_nada():
    assert _digests_estimados(0) == 0
    assert _digests_estimados(-1) == 0


def test_pocas_normas_es_casi_un_mail_por_norma():
    # Con volumen bajo cada coincidencia cae en su propia corrida.
    assert _digests_estimados(1) == 1
    assert _digests_estimados(5) == 5


def test_satura_en_el_techo_y_no_crece_para_siempre():
    # Una alerta anchísima no puede estimar 2.000 mails: el matcher agrupa.
    assert _digests_estimados(5_000) == _TECHO_MAILS_MES
    assert _digests_estimados(50_000) == _TECHO_MAILS_MES


def test_es_monotono():
    valores = [_digests_estimados(n) for n in range(0, 400, 10)]
    assert valores == sorted(valores)


def test_calibrado_contra_produccion():
    """Contrastado el 2026-08-21 con 30 días reales: la mediana de los
    workspaces recibe 18 mails/mes y el más pesado 60. Si el modelo se toca,
    tiene que seguir cayendo cerca de esos números o el preview miente."""
    assert 15 <= _digests_estimados(20) <= 20      # mediana observada: 18
    assert 50 <= _digests_estimados(200) <= 60     # máximo observado: 60


def test_la_estimacion_entra_holgada_en_el_cupo_gratis():
    # Una alerta ancha (200 normas/mes) tiene que seguir entrando en el cupo:
    # si no, el cupo estaría mal calibrado y cortaría en el uso normal.
    assert _digests_estimados(200) < cred.CUPO_POR_DEFECTO
