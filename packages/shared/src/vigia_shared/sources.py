"""Registry central de fuentes de datos.

Única definición del universo de fuentes esperadas. Lo consumen:
- los workers (tasks de ingesta + `check_sources` de frescura), y
- la API (`GET /health/sources` calcula el flag `stale` contra estos SLOs).

Cada entrada declara, además de los campos de `source_catalog`:
- `cadence_hours`: cada cuánto debería correr la ingesta (beat).
- `freshness_slo_days`: máxima antigüedad tolerada de la norma más reciente
  (`MAX(fecha_publicacion)`). Es la señal que detecta el caso "la task corre
  ok pero el dataset upstream dejó de avanzar".
"""
from __future__ import annotations

SOURCES: dict[str, dict] = {
    "infoleg": {
        "code": "infoleg",
        "name": "InfoLEG — Base de legislación nacional (Min. Justicia)",
        "kind": "feed",
        "base_url": "https://datos.jus.gob.ar",
        "cadence_hours": 24,
        # El dataset upstream se refresca ~mensualmente con lag: tolerar hasta 20 días.
        "freshness_slo_days": 20,
    },
    "hcdn_proyectos": {
        "code": "hcdn_proyectos",
        "name": "HCDN — Proyectos parlamentarios (datos.hcdn.gob.ar)",
        "kind": "feed",
        "base_url": "https://datos.hcdn.gob.ar",
        "cadence_hours": 24,
        # El portal de Diputados publica el dataset de forma irregular (baches de
        # 1-2 semanas son normales, p.ej. recesos). 15d evita el ruido de alertas
        # en cada bache habitual; sigue avisando si el atraso es realmente anómalo.
        "freshness_slo_days": 15,
    },
    "senado_proyectos": {
        "code": "senado_proyectos",
        "name": "Senado — Proyectos parlamentarios (buscador HSN)",
        "kind": "scrape",
        "base_url": "https://www.senado.gob.ar",
        "cadence_hours": 24,
        "freshness_slo_days": 10,
    },
    "bora_primera": {
        "code": "bora_primera",
        "name": "Boletín Oficial — Primera Sección (edición del día)",
        "kind": "scrape",
        "base_url": "https://www.boletinoficial.gob.ar",
        "cadence_hours": 24,
        # Publica cada día hábil; 4 días tolera fin de semana largo.
        "freshness_slo_days": 4,
    },
    "hcdn_movimientos": {
        "code": "hcdn_movimientos",
        "name": "HCDN — Movimientos de proyectos (estados de tramitación)",
        "kind": "feed",
        "base_url": "https://datos.hcdn.gob.ar",
        "cadence_hours": 24,
        # No crea normas (actualiza estado de PROYECTO): sin SLO propio.
        "freshness_slo_days": None,
    },
    "bcra_comunicaciones": {
        "code": "bcra_comunicaciones",
        "name": "BCRA — Comunicaciones A (normativa cambiaria y financiera)",
        "kind": "scrape",
        "base_url": "https://www.bcra.gob.ar",
        "cadence_hours": 24,
        # ~5-10 por semana; 10 días tolera semanas quietas.
        "freshness_slo_days": 10,
    },
    "bora_segunda": {
        "code": "bora_segunda",
        "name": "Boletín Oficial — Segunda Sección (avisos societarios)",
        "kind": "scrape",
        "base_url": "https://www.boletinoficial.gob.ar",
        "cadence_hours": 24,
        # Escribe en aviso_societario (no en norma): el SLO de frescura por
        # MAX(fecha_publicacion) no aplica acá; vale el chequeo de cadencia.
        "freshness_slo_days": None,
    },
    "consultas_publicas": {
        "code": "consultas_publicas",
        "name": "Consultas públicas — consultapublica.argentina.gob.ar",
        "kind": "api",
        "base_url": "https://consultapublica.argentina.gob.ar",
        "cadence_hours": 24,
        # ~5-15/mes: una nueva por mes ya es ritmo normal.
        "freshness_slo_days": 60,
    },
    "bocaba": {
        "code": "bocaba",
        "name": "Boletín Oficial — Ciudad de Buenos Aires (CABA)",
        "kind": "api",
        "base_url": "https://api-restboletinoficial.buenosaires.gob.ar",
        "cadence_hours": 24,
        # Publica cada día hábil; 4 días tolera fin de semana largo (igual que BORA 1ª).
        "freshness_slo_days": 4,
    },
    "bopba": {
        "code": "bopba",
        "name": "Boletín Oficial — Provincia de Buenos Aires (sección Oficial)",
        "kind": "scrape",
        "base_url": "https://boletinoficial.gba.gob.ar",
        "cadence_hours": 24,
        # Publica cada día hábil; 4 días tolera fin de semana largo.
        "freshness_slo_days": 4,
    },
    "bicameral_dnu": {
        "code": "bicameral_dnu",
        "name": "Comisión Bicameral DNU — dictámenes (datos.hcdn.gob.ar)",
        "kind": "feed",
        "base_url": "https://datos.hcdn.gob.ar",
        "cadence_hours": 24,
        # No crea normas (actualiza dnu_tracking): sin SLO de frescura propia.
        "freshness_slo_days": None,
    },
}

# Campos que van a la tabla source_catalog (los upserta cada task de ingesta).
_CATALOG_FIELDS = ("code", "name", "kind", "base_url")


def catalog_fields(code: str) -> dict:
    """Subset de SOURCES[code] con el shape que espera `upsert_normas`/`_upsert_source`."""
    src = SOURCES[code]
    return {k: src[k] for k in _CATALOG_FIELDS}
