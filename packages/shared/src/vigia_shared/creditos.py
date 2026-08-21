"""Créditos: cuánto consumió un workspace en el período en curso.

Calca el sistema del proyecto hermano de Políticas Públicas, adaptado a
Postgres y a que acá la unidad es el **workspace** y no la persona.

Las tres decisiones que explican todo lo demás:

1. **Se almacena plata, se muestran créditos.** El contador guarda
   micro-dólares enteros; el crédito es una capa de presentación
   (`micros / MICROS_POR_CREDITO`). Cambiar cuánto vale un crédito es cambiar
   una constante: no hay backfill porque lo guardado sigue siendo plata.

2. **El período va en la clave del contador**, no en un job. El 1° de cada mes
   se escribe en una fila nueva que arranca en cero, y la vieja queda para la
   purga semanal. Eso cubre gratis el cambio de nivel a mitad de mes: un
   workspace que pasa a `base` empieza a contar contra `2026-08q2` y arranca
   limpio, sin ninguna lógica de prorrateo.

3. **Lo que cambia entre niveles no es el tamaño del cupo sino cada cuánto se
   renueva.** Si `base` fuera "el doble de créditos", el aporte se leería como
   lista de precios, que es justo lo que la fundación no hace.

Qué se mide: **solo el mail de alerta**. El corpus —feed, búsqueda, detalle,
`/v1`— no se mide ni se corta nunca. Ver `PRECIO_MICROS`.

Este módulo es aritmética pura, sin I/O: la persistencia vive en
`vigia_shared.creditos_db`.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

#: Cuánto sale cada acción medida, en micro-dólares (millonésimas de dólar).
#:
#: Un digest sale US$0,01. Es precio **cargado**, no marginal: mandar el mail
#: cuesta ~US$0,0005, pero ese número solo tiene sentido porque atrás hay una
#: máquina indexando once fuentes todos los días. Se cobra la parte
#: proporcional de eso, no el SMTP.
#:
#: Hoy hay una sola entrada a propósito. Cuando exista IA on-demand o sync de
#: /v1 por volumen se agregan acá, y el resto del sistema no se entera.
PRECIO_MICROS: dict[str, int] = {"digest": 10_000}

#: Un crédito son US$0,01, o sea exactamente un mail de alerta. Esa
#: equivalencia 1 crédito = 1 mail es lo que hace que el medidor se pueda
#: explicar en una línea; si algún día se separan, hay que reescribir el copy
#: de /apoyar.
MICROS_POR_CREDITO = 10_000

#: Cupo del período. 100 ≈ "unos tres mails por día".
#:
#: Calibrado el 2026-08-21 contra 30 días de producción: de los 110 workspaces
#: que reciben digests, la mediana consume 18 y el más pesado 60. O sea que hoy
#: no le corta a nadie, y es a propósito — el techo está para el crecimiento y
#: para que el aporte signifique algo, no para cobrarle a los que ya están.
CUPO_POR_DEFECTO = 100
VAR_CUPO = "VIGIA_CREDITOS_MES"

#: Día en que arranca la segunda quincena (nivel `base`).
DIA_DE_LA_SEGUNDA_QUINCENA = 16

NIVEL_BASE = "base"
NIVEL_PLENO = "pleno"
NIVELES = (NIVEL_BASE, NIVEL_PLENO)
#: Una marca de aporte sin nivel —las de antes de que existieran los niveles—
#: es plena. Nadie pierde lo que se le prometió porque después exista un nivel
#: más barato.
NIVEL_POR_DEFECTO = NIVEL_PLENO

CONTACTO = "devops@colossuslab.org"


# --------------------------------------------------------------------------- #
# Plata ↔ créditos
# --------------------------------------------------------------------------- #

def micros_de(accion: str, cantidad: int = 1) -> int:
    """Cuánto sale `cantidad` veces `accion`, en micro-dólares.

    Una acción desconocida sale 0: sumar un tipo de consumo nuevo no puede
    romper la ingesta ni cobrar de más por accidente.
    """
    return PRECIO_MICROS.get(accion, 0) * max(0, int(cantidad))


def creditos_de(micros: int | float | None) -> float:
    """Micro-dólares a créditos, con un decimal (lo que se muestra)."""
    return round(float(micros or 0) / MICROS_POR_CREDITO, 1)


def cupo_del_periodo() -> int:
    """Cupo vigente. Se relee del entorno para poder bajarlo sin redeploy."""
    try:
        return max(0, int(os.environ.get(VAR_CUPO, "") or CUPO_POR_DEFECTO))
    except ValueError:
        return CUPO_POR_DEFECTO


# --------------------------------------------------------------------------- #
# Nivel de aporte
# --------------------------------------------------------------------------- #

def nivel_de(
    plan: str | None, aporte: dict | None = None, hoy: date | None = None
) -> str | None:
    """Nivel vigente del workspace, o None si no tiene aporte activo.

    El vencimiento es lazy: se evalúa acá en cada request y en cada corrida del
    matcher, así que no hace falta ningún cron que expire nada.
    """
    if not plan or plan not in NIVELES:
        return None
    hasta = (aporte or {}).get("hasta")
    if hasta:
        try:
            if date.fromisoformat(str(hasta)[:10]) < (hoy or _hoy()):
                return None
        except ValueError:
            return None  # fecha corrupta → fail closed
    return plan


# --------------------------------------------------------------------------- #
# Período
# --------------------------------------------------------------------------- #

def _hoy() -> date:
    return datetime.now(timezone.utc).date()


def mes_de(hoy: date | None = None) -> str:
    return (hoy or _hoy()).strftime("%Y-%m")


def periodo_de(
    plan: str | None = None, aporte: dict | None = None, hoy: date | None = None
) -> str:
    """Clave del período contra el que cuenta este workspace.

    OJO: tiene que dar lo mismo en las dos puntas —la que lee el saldo y la que
    cobra—. Si una mira el nivel y la otra no, se cuenta contra claves
    distintas y el saldo miente.
    """
    hoy = hoy or _hoy()
    if nivel_de(plan, aporte, hoy) == NIVEL_BASE:
        return f"{mes_de(hoy)}q{1 if hoy.day < DIA_DE_LA_SEGUNDA_QUINCENA else 2}"
    return mes_de(hoy)


def renueva_el(
    plan: str | None = None, aporte: dict | None = None, hoy: date | None = None
) -> date:
    """Primer día del próximo período."""
    hoy = hoy or _hoy()
    if nivel_de(plan, aporte, hoy) == NIVEL_BASE and hoy.day < DIA_DE_LA_SEGUNDA_QUINCENA:
        return hoy.replace(day=DIA_DE_LA_SEGUNDA_QUINCENA)
    # Primer día del mes que viene. Sumarle 4 días al 28 siempre cae adentro
    # del mes siguiente, incluso en febrero.
    return (hoy.replace(day=28) + timedelta(days=4)).replace(day=1)


# --------------------------------------------------------------------------- #
# Estado (lo que ve la web)
# --------------------------------------------------------------------------- #

def estado(
    micros_usados: int | None,
    plan: str | None = None,
    aporte: dict | None = None,
    hoy: date | None = None,
) -> dict:
    """Lo que la web muestra: usados, cupo, si queda, nivel y cuándo renueva.

    `disponibles is None` significa "sin cupo" (nivel pleno) y es distinto de
    cero: el front discrimina por eso, así que no colapsarlo a 0.
    """
    hoy = hoy or _hoy()
    nivel = nivel_de(plan, aporte, hoy)
    sin_cupo = nivel == NIVEL_PLENO
    cupo = cupo_del_periodo()
    usados = creditos_de(micros_usados)
    return {
        "usados": usados,
        "cupo": cupo,
        "disponibles": None if sin_cupo else max(0.0, round(cupo - usados, 1)),
        "agotados": (not sin_cupo) and (micros_usados or 0) >= cupo * MICROS_POR_CREDITO,
        "nivel": nivel,
        "quincenal": nivel == NIVEL_BASE,
        "renueva": renueva_el(plan, aporte, hoy).isoformat(),
        "contacto": CONTACTO,
    }
