# Vigía — guía para Claude

Plataforma de inteligencia legislativa y regulatoria argentina (Colossus Lab,
familia OpenArg). Monorepo full-stack **en producción**:

- **Web**: https://vigia.openarg.org (Vercel, proyecto `colossus-lab/vigia`, Root Directory `apps/web`)
- **API**: https://vigia-api.openarg.org (EC2 all-in-one, us-east-1)
- **Datos**: ~533k normas (InfoLEG completo + proyectos HCDN), actualización automática diaria.

La arquitectura calca el patrón del lab (InvestArg/OpenArg): FastAPI async +
SQLAlchemy 2.0 + Postgres 16/pgvector + Celery/Redis + Next.js 16 + NextAuth.
**No inventar stack nuevo: ante la duda, mirar cómo lo hace `../investarg`.**

## Mapa del monorepo

```
apps/api/       FastAPI (vigia_api) — routers: health, normas, search (FTS), stats, auth, workspaces, invitations, alerts
apps/web/       Next.js 16 App Router (JSX, no TS) — tema OpenArg dark + paleta Argentina
apps/workers/   Celery (vigia_workers) — tasks de ingesta + matching de alertas + beat schedule
packages/shared/      modelos SQLAlchemy + schemas Pydantic + constantes (vigia_shared)
packages/connectors/  InfoLEG + HCDN (vigia_connectors)
db/alembic/     migraciones (0001 inicial, 0002 multitenant, 0003 alertas)
infra/          Caddyfile, ec2-user-data.sh, DEPLOY.md (runbook completo)
```

## Comandos dev (Windows, PowerShell)

```powershell
docker compose up -d db redis                  # Postgres pgvector + Redis
.venv\Scripts\pip install -e packages\shared -e packages\connectors -e apps\workers -e apps\api
$env:DATABASE_URL="postgresql+asyncpg://vigia:vigia@localhost:5432/vigia"
.venv\Scripts\alembic -c db\alembic.ini upgrade head
.venv\Scripts\python -c "from vigia_workers.tasks import ingest_infoleg as t; print(t())"   # sample dev (~990, datos VIEJOS 2022)
.venv\Scripts\python -m uvicorn vigia_api.main:app --reload --port 8000
cd apps\web; pnpm dev                          # http://localhost:3000
```

Build web: `pnpm build` en `apps/web`. Tests: `pytest packages/connectors/tests apps/api/tests` (cuando existan).

## Deploy a producción

Push a `main` → CI `build-images` publica `ghcr.io/colossus-lab/vigia-{api,workers}` (públicas).
En el EC2 (`ssh -i ~/.ssh/<key>.pem ec2-user@<EIP>`, repo clonado en `~/vigia`):

```bash
cd vigia && git pull
docker compose -f docker-compose.prod.yml --profile local-data pull
docker compose -f docker-compose.prod.yml --profile local-data up -d --no-build
```

El web se redeploya solo con cada push (Vercel Git integration). Runbook completo: `infra/DEPLOY.md`.

## Gotchas no obvios (aprendidos a golpes)

- **DNU**: InfoLEG los clasifica `tipo_norma="Decreto"` + `clase_norma="DNU"`. El slug se decide mirando `clase_norma` PRIMERO (`infoleg.py:tipo_slug`).
- **PROYECTO**: no existe en InfoLEG; viene de `datos.hcdn.gob.ar` (CKAN `proyectos-parlamentarios`). La URL del CSV **cambia de nombre por versión** → siempre resolverla vía `package_show` (ya lo hace `HcdnClient.resolve_csv_url`).
- **Sample vs full**: `ingest_infoleg` (sample) es un CSV estático de 2022 — solo para dev. La frescura real la da `ingest_infoleg_full` (beat diario 03:00 ART). HCDN diario 08:00 ART. Alertas cada hora.
- **Batch de upsert máx 1000 filas**: asyncpg limita 32.767 parámetros bind por statement (~17 columnas/fila). No subir `_FULL_BATCH`.
- **Upserts idempotentes** por `(source_id, external_id)` con dedup intra-batch (ON CONFLICT no tolera duplicados en el mismo INSERT).
- **Compose prod**: `environment:` pisa `env_file:` y `${VAR}` se interpola desde `.env` (no desde env_file) → en el EC2 existe `.env` como copia de `.env.production`. No borrarla.
- **`search_vector`** es columna GENERATED (tsvector spanish, migración 0001) — no escribirla desde el ORM.
- **Windows**: `aws.exe` emite la key SSH con CRLF (rompe libcrypto — limpiar con `tr -d '\r'`); Git Bash convierte `/dev/...` en paths Windows (usar `MSYS_NO_PATHCONV=1`); el venv usa Python 3.14.
- **Auth**: `AUTH_ENABLED=false` (default) = modo demo público. Los endpoints de datos son públicos SIEMPRE; el gating aplica solo a `/workspaces`, `/invitations`, `/alerts`. El JWT lo firma la API en `/auth/sync` (server-to-server con `AUTH_SECRET`).
- **NextAuth v5-beta + Next 16**: known issue con `headers()` async al activar OAuth real — puede requerir bump de next-auth (documentado en `../investarg`).
- **Preview/screenshots en dev**: el cliente next-auth + TypingDemo impiden el "network idle" — verificar por DOM (`preview_eval`) en vez de screenshot.
- **BORA**: sin API — scrape del HTML server-rendered (`/seccion/{seccion}/{yyyymmdd}` + detalle `#cuerpoDetalleAviso`). IDs de 2ª sección alfanuméricos (`A1500779`); los rubros son headers `h5.seccion-rubro` intercalados (se trackean posicionalmente). Los DNU salen como "Decreto": se promueven mirando el texto del detalle (art. 99 inc. 3).
- **Dedup BORA↔InfoLEG**: `reconcile_bora_infoleg` borra la fila BORA cuando llega la gemela InfoLEG, trasplantando antes los `alerta_match` con `notified=true` (anti doble-notificación). Solo LEY/DECRETO/DNU, con guard de instrumento (las Decisiones Administrativas numeran aparte).
- **Orden de beats importa**: `ingest_hcdn_proyectos` (08:00) pisa `norma.estado` a diario; `ingest_hcdn_movimientos` (08:30) lo re-deriva. No invertirlos.
- **Fuentes nuevas**: runbook en `infra/DEPLOY.md` (dry-run → backfill → `match_alertas(notify=False)` → beat). Registry con SLOs en `vigia_shared/sources.py`; estado operativo sin ssh en `GET /health/sources`.
- **BORA 2ª NO entra a `norma`**: va a `aviso_societario` (tabla y FTS propios, router `/avisos`, página "Radar societario") para no contaminar feed/stats/alertas.
- **Free trial**: 30 días por workspace (`Workspace.created_at` + `VIGIA_TRIAL_DAYS`); al vencer, 402 `trial_expired` en endpoints gated + cartel inamovible en el web. Membresía manual: `UPDATE workspace SET plan='member'` (runbook en DEPLOY.md).

## Diseño / UX

Tema OpenArg calcado de `../Open Arg/openarg_frontend` (spec: `designNuevaOpenArgTheme.md` ahí):
dark cinematic `#06090F/#0D1117`, celeste `#74ACDF` + sol `#F6B40E`, tints rgba para badges,
franja-bandera, Familjen Grotesk para headlines, JetBrains Mono para datos, FadeIn on-scroll
con `prefers-reduced-motion`. El `<em>` en títulos display va en sol itálica.

## Roadmap pendiente

El roadmap interno (`PLAN.md`) vive solo local, fuera del repo público.
