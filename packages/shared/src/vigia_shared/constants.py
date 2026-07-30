"""Constantes de dominio de Vigía.

Portadas del frontend mock original (`src/data/mockData.js`) para que backend
y frontend compartan el mismo vocabulario de tipos/sectores/jurisdicciones.
"""
from __future__ import annotations

# Tipo de norma -> metadata para UI. El `slug` es lo que se guarda en `norma.tipo`.
TIPOS_NORMA: dict[str, dict[str, str]] = {
    "DNU": {"label": "DNU", "description": "Decreto de Necesidad y Urgencia"},
    "DECRETO": {"label": "Decreto", "description": "Decreto del Poder Ejecutivo"},
    "LEY": {"label": "Ley", "description": "Ley sancionada por el Congreso"},
    "RESOLUCION": {"label": "Resolución", "description": "Resolución ministerial"},
    "DISPOSICION": {"label": "Disposición", "description": "Disposición administrativa"},
    "PROYECTO": {"label": "Proyecto", "description": "Proyecto de ley en trámite"},
    "COMUNICACION": {"label": "Comunicación", "description": "Comunicación del BCRA (serie A)"},
    "CONSULTA": {"label": "Consulta", "description": "Consulta pública / anteproyecto en consulta"},
    "OTRA": {"label": "Otra", "description": "Otra norma"},
}

JURISDICCIONES: list[str] = [
    "Nacional", "Buenos Aires", "CABA", "Córdoba", "Santa Fe",
    "Mendoza", "Tucumán", "Entre Ríos",
]

SECTORES: list[str] = [
    "Economía", "Energía", "Salud", "Educación", "Justicia", "Trabajo",
    "Ambiente", "Tecnología", "Comercio", "Transporte", "Minería", "Agro",
    "Defensa", "Seguridad",
]

IMPACTOS: list[str] = ["alto", "medio", "bajo"]

# Roles de membresía en un workspace. Hasta ahora solo existían como
# CheckConstraint en la base (`ck_member_role`, `ck_invite_role`) y como strings
# sueltos en los routers; centralizarlos evita que un typo pase silencioso.
ROL_OWNER = "owner"
ROL_ADMIN = "admin"
ROL_VIEWER = "viewer"
ROLES: tuple[str, ...] = (ROL_OWNER, ROL_ADMIN, ROL_VIEWER)

# Quiénes pueden escribir en los recursos del workspace (alertas, onboarding).
# El `viewer` lee todo pero no modifica nada.
ROLES_ESCRITURA: tuple[str, ...] = (ROL_OWNER, ROL_ADMIN)

# Estados de tramitación de PROYECTO derivados de los movimientos HCDN
# (vigia_connectors.hcdn.derivar_estado). "En trámite" es el default al ingestar.
ESTADOS_PROYECTO: list[str] = [
    "En trámite", "En comisión", "Archivado", "Con dictamen",
    "Aprobado", "Media sanción", "Sancionado",
]
