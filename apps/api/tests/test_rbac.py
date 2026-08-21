"""Regresiones del hallazgo #6: un `viewer` podía escribir en el workspace.

Dos ángulos, los dos herméticos (sin base, como el resto de la suite):

1. La dependency `require_role` en aislamiento: quién pasa y quién come 403.
2. Un test ESTRUCTURAL que recorre las rutas de la app y verifica que los
   endpoints de escritura tengan `require_escritura` realmente cableada. Sin
   esto, alguien puede volver a poner `require_active_plan` en un endpoint y los
   tests de (1) seguirían en verde sin notar nada.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from fastapi.dependencies.utils import get_dependant
from fastapi.routing import APIRoute

from vigia_api.core.security import WorkspaceContext, require_escritura, require_role
from vigia_api.main import create_app
from vigia_shared.constants import ROL_ADMIN, ROL_OWNER, ROL_VIEWER

from conftest import rutas_de


def _ctx(role: str) -> WorkspaceContext:
    return WorkspaceContext(user_id=1, workspace_id=1, role=role, plan="free")


# --- 1. la dependency en aislamiento ---------------------------------------


@pytest.mark.parametrize("role", [ROL_OWNER, ROL_ADMIN])
def test_owner_y_admin_pueden_escribir(role):
    ctx = _ctx(role)
    assert asyncio.run(require_escritura(ctx)) is ctx


def test_viewer_no_puede_escribir():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_escritura(_ctx(ROL_VIEWER)))
    assert exc.value.status_code == 403
    # El detalle no cambia respecto de los chequeos inline que había antes en
    # workspaces.py: el front ya lo mostraba así.
    assert exc.value.detail == "requires_owner_or_admin"


def test_rol_desconocido_no_pasa():
    # Defensa contra un rol nuevo agregado a la base sin actualizar la allowlist:
    # el default es negar, no permitir.
    for role in ("", "editor", "superadmin", "OWNER"):
        with pytest.raises(HTTPException):
            asyncio.run(require_escritura(_ctx(role)))


def test_require_role_arma_el_detalle():
    dep = require_role(ROL_OWNER)
    assert asyncio.run(dep(_ctx(ROL_OWNER))).role == ROL_OWNER
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(_ctx(ROL_ADMIN)))
    assert exc.value.detail == "requires_owner"


# --- 2. el cableado real de los endpoints ----------------------------------


def _deps_de(route: APIRoute) -> set:
    """Todas las dependencies de una ruta, recursivo."""
    encontradas = set()

    def _walk(dependant):
        for d in dependant.dependencies:
            if d.call is not None:
                encontradas.add(d.call)
            _walk(d)

    _walk(get_dependant(path=route.path_format, call=route.endpoint))
    _walk(route.dependant)
    return encontradas


# (método, path) de todo lo que escribe en recursos del workspace.
ESCRITURA = [
    ("POST", "/alerts"),
    ("PATCH", "/alerts/{alerta_id}"),
    ("DELETE", "/alerts/{alerta_id}"),
    ("POST", "/workspaces/me/onboarding"),
    ("POST", "/workspaces/me/invitations"),
    ("DELETE", "/workspaces/me/members/{user_id}"),
]


@pytest.mark.parametrize("metodo,path", ESCRITURA)
def test_endpoints_de_escritura_exigen_rol(metodo, path):
    app = create_app()
    rutas = [
        r for r in rutas_de(app)
        if r.path == path and metodo in (r.methods or ())
    ]
    assert rutas, f"no existe {metodo} {path}"
    assert require_escritura in _deps_de(rutas[0]), (
        f"{metodo} {path} no exige rol de escritura — un viewer podría escribir"
    )


# Solo lectura o acciones sobre uno mismo: NO deben exigir rol de escritura.
# Si alguien se los agrega, un viewer deja de poder usar la plataforma.
SIN_ROL = [
    ("POST", "/alerts/preview"),   # estimar volumen es lectura
    ("GET", "/alerts"),
    ("POST", "/workspaces/me/leave"),
    ("DELETE", "/account"),        # derecho de supresión propio (Ley 25.326)
]


@pytest.mark.parametrize("metodo,path", SIN_ROL)
def test_lectura_y_acciones_propias_no_exigen_rol(metodo, path):
    app = create_app()
    rutas = [
        r for r in rutas_de(app)
        if r.path == path and metodo in (r.methods or ())
    ]
    assert rutas, f"no existe {metodo} {path}"
    assert require_escritura not in _deps_de(rutas[0]), (
        f"{metodo} {path} exige rol de escritura y no debería"
    )
