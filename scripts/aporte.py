#!/usr/bin/env python
"""Activa, renueva o quita el aporte de un workspace.

La marca de aporte la pone el laboratorio, NUNCA la web: no hay webhook de
Mercado Pago, así que el circuito real es que la persona se suscribe, nos
escribe con el mail con el que entra a Vigía —que no siempre es el de MP— y
alguien corre esto.

    python scripts/aporte.py --listar
    python scripts/aporte.py ana@ministerio.gob.ar --nivel base
    python scripts/aporte.py mi-workspace --nivel pleno --hasta 2026-12-31
    python scripts/aporte.py mi-workspace --quitar

El destinatario puede ser el slug del workspace o el email de un miembro (que
es lo que la persona nos manda). Con el email se resuelve su workspace propio;
si es miembro de varios, el script los lista y no toca nada — elegir por slug.

Niveles (ver `vigia_shared.creditos`):
  base   → el cupo se renueva cada quincena (el 1 y el 16) en vez de por mes
  pleno  → sin cupo

Es idempotente: correrlo dos veces deja lo mismo. `--hasta` ausente = no vence.

En producción:
    docker compose -f docker-compose.prod.yml exec api python scripts/aporte.py ...
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime, timezone

from sqlalchemy import text

from vigia_shared import creditos as cred
from vigia_shared.db import session_scope

ORIGENES = ("mercado pago", "transferencia", "a mano")


async def _resolver(session, destinatario: str) -> tuple[int, str, str] | None:
    """(id, slug, name) del workspace, o None si no se pudo resolver."""
    if "@" not in destinatario:
        row = (
            await session.execute(
                text("SELECT id, slug, name FROM workspace WHERE slug = :s"),
                {"s": destinatario},
            )
        ).first()
        if row is None:
            print(f"no existe el workspace con slug {destinatario!r}", file=sys.stderr)
            return None
        return int(row[0]), row[1], row[2]

    filas = (
        await session.execute(
            text(
                """
                SELECT w.id, w.slug, w.name, m.role
                FROM workspace w
                JOIN workspace_member m ON m.workspace_id = w.id
                JOIN app_user u ON u.id = m.user_id
                WHERE lower(u.email) = lower(:e)
                ORDER BY w.id
                """
            ),
            {"e": destinatario},
        )
    ).all()
    if not filas:
        print(
            f"no hay ningún workspace para {destinatario!r}. "
            "¿Entró alguna vez a Vigía con ese mail?",
            file=sys.stderr,
        )
        return None
    if len(filas) > 1:
        print(f"{destinatario} es miembro de {len(filas)} workspaces:", file=sys.stderr)
        for f in filas:
            print(f"  {f[1]:<24} {f[2]}  ({f[3]})", file=sys.stderr)
        print("elegí uno por slug y volvé a correrlo.", file=sys.stderr)
        return None
    return int(filas[0][0]), filas[0][1], filas[0][2]


async def listar() -> int:
    async with session_scope() as session:
        filas = (
            await session.execute(
                text(
                    "SELECT slug, name, plan, aporte FROM workspace "
                    "WHERE plan <> 'free' ORDER BY slug"
                )
            )
        ).all()
    if not filas:
        print("no hay ningún workspace con aporte activo.")
        return 0
    hoy = datetime.now(timezone.utc).date()
    print(f"{'SLUG':<24} {'NIVEL':<7} {'DESDE':<11} {'HASTA':<11} {'VIGENTE':<8} NOMBRE")
    for slug, name, plan, aporte in filas:
        aporte = aporte or {}
        vigente = cred.nivel_de(plan, aporte, hoy) is not None
        print(
            f"{slug:<24} {plan:<7} {str(aporte.get('desde') or '-'):<11} "
            f"{str(aporte.get('hasta') or 'no vence'):<11} "
            f"{('sí' if vigente else 'VENCIDO'):<8} {name}"
        )
    return 0


async def aplicar(destinatario: str, nivel: str | None, hasta: str | None, origen: str) -> int:
    async with session_scope() as session:
        resuelto = await _resolver(session, destinatario)
        if resuelto is None:
            return 1
        ws_id, slug, name = resuelto

        if nivel is None:  # --quitar
            await session.execute(
                text("UPDATE workspace SET plan = 'free', aporte = NULL WHERE id = :i"),
                {"i": ws_id},
            )
            print(f"{slug} ({name}): aporte quitado, vuelve al cupo gratis.")
            return 0

        previo = (
            await session.execute(
                text("SELECT aporte FROM workspace WHERE id = :i"), {"i": ws_id}
            )
        ).scalar()
        marca = {
            # `desde` se conserva de la marca previa: renovar o subir de nivel no
            # borra desde cuándo esta persona banca el proyecto.
            "desde": (previo or {}).get("desde") or date.today().isoformat(),
            "origen": origen,
        }
        if hasta:
            marca["hasta"] = hasta

        await session.execute(
            text("UPDATE workspace SET plan = :p, aporte = CAST(:a AS jsonb) WHERE id = :i"),
            {"p": nivel, "a": __import__("json").dumps(marca), "i": ws_id},
        )
        vence = f", vence el {hasta}" if hasta else ", sin vencimiento"
        print(f"{slug} ({name}): nivel {nivel}{vence}.")
        if nivel == cred.NIVEL_BASE:
            print("  el cupo se le renueva el 1 y el 16 de cada mes.")
        else:
            print("  sin cupo: no se le cuentan créditos.")
        return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("destinatario", nargs="?", help="slug del workspace o email de un miembro")
    p.add_argument("--nivel", choices=list(cred.NIVELES), help="nivel de aporte a activar")
    p.add_argument("--hasta", metavar="YYYY-MM-DD", help="hasta cuándo vale (default: no vence)")
    p.add_argument("--origen", choices=ORIGENES, default="mercado pago")
    p.add_argument("--quitar", action="store_true", help="vuelve el workspace a 'free'")
    p.add_argument("--listar", action="store_true", help="lista los aportes activos")
    a = p.parse_args()

    if a.listar:
        return asyncio.run(listar())
    if not a.destinatario:
        p.error("falta el destinatario (o usá --listar)")
    if a.quitar:
        return asyncio.run(aplicar(a.destinatario, None, None, a.origen))
    if not a.nivel:
        p.error("falta --nivel (o --quitar)")
    if a.hasta:
        try:
            date.fromisoformat(a.hasta)
        except ValueError:
            p.error(f"--hasta tiene que ser YYYY-MM-DD, no {a.hasta!r}")
    return asyncio.run(aplicar(a.destinatario, a.nivel, a.hasta, a.origen))


if __name__ == "__main__":
    raise SystemExit(main())
