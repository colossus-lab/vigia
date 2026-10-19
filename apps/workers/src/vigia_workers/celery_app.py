"""Celery application + beat schedule para la ingesta de Vigía."""
from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "vigia",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "vigia_workers.tasks",
        "vigia_workers.congreso_senado",
        "vigia_workers.alerts",
        "vigia_workers.freshness",
        "vigia_workers.reconcile",
        "vigia_workers.bicameral",
        "vigia_workers.movimientos",
        "vigia_workers.congreso_hcdn",
        "vigia_workers.societario",
        "vigia_workers.maintenance",
    ],
)

# Sentry — no-op si falta SENTRY_DSN.
_sentry_dsn = os.environ.get("SENTRY_DSN")
if _sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration

        sentry_sdk.init(
            dsn=_sentry_dsn,
            integrations=[CeleryIntegration()],
            traces_sample_rate=0.05,
            environment=os.environ.get("VIGIA_ENV", "dev"),
        )
    except Exception as e:  # pragma: no cover
        print(f"[sentry] init failed: {e!r}")

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    timezone="America/Argentina/Buenos_Aires",
    enable_utc=False,
    beat_schedule={
        # InfoLEG / Boletín Oficial — corpus completo (incluye lo último publicado),
        # diario 03:00 ART. El dataset oficial se refresca semanalmente, correrlo
        # a diario garantiza tomar cada actualización apenas sale.
        "ingest-infoleg-full": {
            "task": "vigia_workers.tasks.ingest_infoleg_full",
            "schedule": crontab(hour=3, minute=0),
        },
        # Reconcile BORA↔InfoLEG post corpus full: la gemela InfoLEG reemplaza
        # a la fila BORA (anti-duplicados del feed).
        "reconcile-bora-infoleg": {
            "task": "vigia_workers.reconcile.reconcile_bora_infoleg",
            "schedule": crontab(hour=4, minute=30),
        },
        # BORA 1ª sección — frescura diaria real (el BO publica de madrugada).
        # Retry 12:00 por si la edición sale tarde. Lookback 5 días idempotente.
        "ingest-bora-primera": {
            "task": "vigia_workers.tasks.ingest_bora_primera",
            "schedule": crontab(hour=7, minute=0),
        },
        "ingest-bora-primera-retry": {
            "task": "vigia_workers.tasks.ingest_bora_primera",
            "schedule": crontab(hour=12, minute=0),
        },
        # HCDN proyectos parlamentarios — el dataset se actualiza a diario.
        "ingest-hcdn-proyectos": {
            "task": "vigia_workers.tasks.ingest_hcdn_proyectos",
            "schedule": crontab(hour=8, minute=0),
        },
        # Movimientos de proyectos HCDN — DEBE correr después de
        # ingest-hcdn-proyectos (08:00), que pisa `estado` con "En trámite";
        # esta task lo re-deriva (el pisado se auto-repara a diario).
        "ingest-hcdn-movimientos": {
            "task": "vigia_workers.movimientos.ingest_hcdn_movimientos",
            "schedule": crontab(hour=8, minute=30),
        },
        # Congreso — Diputados (tablas propias, no norma). Todo DESPUÉS de la
        # ventana de proyectos/movimientos (08:00–08:30), sin competir con ella.
        # Agenda de comisiones (semana en curso): mañana y tarde.
        "ingest-hcdn-agenda": {
            "task": "vigia_workers.congreso_hcdn.ingest_hcdn_agenda",
            "schedule": crontab(hour=8, minute=40),
        },
        "ingest-hcdn-agenda-tarde": {
            "task": "vigia_workers.congreso_hcdn.ingest_hcdn_agenda",
            "schedule": crontab(hour=18, minute=10),
        },
        # Sesiones (CKAN + listado del sitio) y, después, sus asuntos tratados:
        # asuntos necesita la sesión cargada para la FK.
        "ingest-hcdn-sesiones": {
            "task": "vigia_workers.congreso_hcdn.ingest_hcdn_sesiones",
            "schedule": crontab(hour=9, minute=40),
        },
        "ingest-hcdn-asuntos": {
            "task": "vigia_workers.congreso_hcdn.ingest_hcdn_asuntos",
            "schedule": crontab(hour=9, minute=50),
        },
        # Diputados en funciones — semanal, lunes 06:15 (fuera de toda ventana).
        "ingest-hcdn-legisladores": {
            "task": "vigia_workers.congreso_hcdn.ingest_hcdn_legisladores",
            "schedule": crontab(day_of_week=1, hour=6, minute=15),
        },
        # Senado — proyectos recientes (scrape del buscador HSN). Orígenes
        # S/PE/JGM/OV (los venidos de Diputados ya entran por hcdn-proyectos). Fuera de la ventana
        # HCDN (08:00–08:30) para no competir por el worker.
        "ingest-senado-proyectos": {
            "task": "vigia_workers.tasks.ingest_senado_proyectos",
            "schedule": crontab(hour=8, minute=45),
        },
        # Senado — actividad (vigia_workers.congreso_senado) → tablas del Congreso.
        # Votaciones dos veces: las sesiones terminan de madrugada y el acta se
        # carga a la mañana; la de la noche toma las de una sesión diurna.
        "ingest-senado-votaciones": {
            "task": "vigia_workers.congreso_senado.ingest_senado_votaciones",
            "schedule": crontab(hour=7, minute=30),
        },
        "ingest-senado-votaciones-noche": {
            "task": "vigia_workers.congreso_senado.ingest_senado_votaciones",
            "schedule": crontab(hour=23, minute=30),
        },
        # Agenda de comisiones: a la mañana y a la tarde (se cargan reuniones
        # durante el día para los días siguientes).
        "ingest-senado-agenda": {
            "task": "vigia_workers.congreso_senado.ingest_senado_agenda",
            "schedule": crontab(hour=8, minute=50),
        },
        "ingest-senado-agenda-tarde": {
            "task": "vigia_workers.congreso_senado.ingest_senado_agenda",
            "schedule": crontab(hour=18, minute=0),
        },
        # Sesiones: después de votaciones, así `_vincular_sesiones` engancha
        # las votaciones de la madrugada con su sesión.
        "ingest-senado-sesiones": {
            "task": "vigia_workers.congreso_senado.ingest_senado_sesiones",
            "schedule": crontab(hour=9, minute=10),
        },
        # Senadores en ejercicio + ex senadores — semanal, lunes 06:00 ART.
        "ingest-senado-legisladores": {
            "task": "vigia_workers.congreso_senado.ingest_senado_legisladores",
            "schedule": crontab(day_of_week=1, hour=6, minute=0),
        },
        # Dictámenes de la Comisión Bicameral DNU (HCDN CKAN) — diario.
        # Después de hcdn-proyectos (08:00): el join usa los proyectos del día.
        "ingest-bicameral-dnu": {
            "task": "vigia_workers.bicameral.ingest_bicameral_dnu",
            "schedule": crontab(hour=9, minute=30),
        },
        # BORA 2ª sección → aviso_societario (Radar societario) — diario,
        # separado de la 1ª para aislar fallos y carga.
        "ingest-bora-segunda": {
            "task": "vigia_workers.societario.ingest_bora_segunda",
            "schedule": crontab(hour=10, minute=30),
        },
        # BO CABA (API REST) — frescura diaria. Después de BORA 1ª (07:00).
        "ingest-bocaba": {
            "task": "vigia_workers.tasks.ingest_bocaba",
            "schedule": crontab(hour=7, minute=15),
        },
        # BO Provincia de Buenos Aires (sección OFICIAL, PDF) — frescura diaria.
        "ingest-pba": {
            "task": "vigia_workers.tasks.ingest_pba",
            "schedule": crontab(hour=9, minute=0),
        },
        # Consultas públicas (señal temprana) — diario al mediodía.
        "ingest-consultas-publicas": {
            "task": "vigia_workers.tasks.ingest_consultas_publicas",
            "schedule": crontab(hour=12, minute=0),
        },
        # Comunicaciones A del BCRA — diario post-publicación (patrón InvestArg).
        "ingest-bcra-comunicaciones": {
            "task": "vigia_workers.tasks.ingest_bcra_comunicaciones",
            "schedule": crontab(hour=20, minute=30),
        },
        # Matching de alertas + notificaciones — cada hora.
        "match-alertas": {
            "task": "vigia_workers.alerts.match_alertas",
            "schedule": crontab(minute=15),
        },
        # Frescura de fuentes contra SLOs (vigia_shared.sources) — cada 6 h.
        # Detecta datasets estancados aunque la task corra "ok".
        "check-sources": {
            "task": "vigia_workers.freshness.check_sources",
            "schedule": crontab(hour="*/6", minute=45),
        },
        # Retención de audit_log (IP/user-agent) — semanal, domingo 05:00 ART.
        # Borra registros más viejos que VIGIA_AUDIT_RETENTION_DAYS (Ley 25.326,
        # art. 4: limitación temporal). Fuera de la ventana de ingesta.
        "purge-audit-log": {
            "task": "vigia_workers.maintenance.purge_audit_log",
            "schedule": crontab(day_of_week=0, hour=5, minute=0),
        },
        # Contadores de créditos de períodos viejos — semanal, domingo 05:15 ART.
        # Va después del purge de audit_log y fuera de la ventana de ingesta.
        "purge-creditos": {
            "task": "vigia_workers.maintenance.purge_creditos",
            "schedule": crontab(day_of_week=0, hour=5, minute=15),
        },
    },
)
