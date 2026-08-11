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
- **`/docs`, `/redoc` y `/openapi.json` están CERRADOS por default** (404). Se
  prenden solo con `VIGIA_DOCS=true`, que se setea en dev y nunca en producción:
  publicaban el mapa completo de la API. Si la variable falta, quedan cerrados —
  el lado seguro del error. Ojo: diagnosticar la API leyendo `/openapi.json` ya
  no funciona contra prod.
- **`AUTH_SECRET` con `AUTH_ENABLED=true` aborta el arranque** si está vacío, es
  un placeholder conocido (`dev-only-change-me`, que vive en este repo público) o
  mide menos de 32 caracteres. Preferimos que la API no levante antes que firmar
  JWT con un secreto que cualquiera puede leer en GitHub.
- **El JWT de la API NO llega al browser**: el web pega a los endpoints gateados
  vía el BFF `apps/web/app/api/vigia/[...path]/route.js`, que descifra la cookie
  de NextAuth con `getToken()` e inyecta el bearer **server-side**. `authedFetch`
  recibe `(path, init)` — sin token. Para sumar un endpoint hay que agregarlo a
  la **allowlist** del handler: no es un proxy genérico a propósito (un rewrite
  `:path*` ya se removió una vez por dejar un proxy abierto en Vercel). El
  secreto del handler tiene que ser el mismo `AUTH_SECRET` que usa `auth.js`, o
  `getToken()` devuelve null en silencio y todos comen 401.
- **`getToken()` necesita `secureCookie`** — esto ya rompió producción una vez.
  Su default es `false`, y de ahí salen el nombre de cookie que busca
  (`authjs.session-token`) **y** el salt con que la descifra. En HTTPS la cookie
  es `__Secure-authjs.session-token`: sin el flag no la encuentra ni podría
  abrirla, y devuelve null **sin error**. El handler lo deduce de las cookies que
  llegan. Regresión: `pnpm test:bff` en `apps/web` — cifra una cookie con la
  criptografía real, sin browser ni sesión de Google.
- **Un cambio que toque la sesión no se prueba sin loguearse.** Build, tests y
  render pasan igual con el BFF roto. Va por rama → preview de Vercel → probar
  con sesión real → recién ahí a `main`. Ojo: en la preview **no cargan las
  normativas**, porque el browser las pide directo a la API y su origen no está
  en `API_CORS_ORIGINS`. Eso es esperable y no es un bug: lo que pasa por el BFF
  es same-origin y sí funciona.
- **Rate limiting** (`apps/api/src/vigia_api/core/ratelimit.py`): en memoria, va
  como *dependency* y no como middleware — registrado después de `CORSMiddleware`
  quedaría por fuera y los 429 saldrían sin headers CORS. Solo mutaciones y
  endpoints caros; los GET públicos **no** se limitan porque el SSR de Vercel
  llega desde pocas IPs y las estrangularía. En `/auth/sync` se limitan **fallos**
  y no intentos, por el mismo motivo. Se apaga con `RATELIMIT_ENABLED=false`.
  Caddy no sirve para esto: la imagen stock no trae módulo de rate limit.
- **Escritura en el workspace exige rol** `owner|admin` (`require_escritura`).
  `require_active_plan` NO valida rol — no usarla para endpoints que escriben.
- **Auth**: `AUTH_ENABLED=false` (default) = modo demo público. Los endpoints de datos son públicos SIEMPRE; el gating aplica solo a `/workspaces`, `/invitations`, `/alerts`. El JWT lo firma la API en `/auth/sync` (server-to-server con `AUTH_SECRET`).
- **NextAuth v5-beta + Next 16**: known issue con `headers()` async al activar OAuth real — puede requerir bump de next-auth (documentado en `../investarg`).
- **Preview/screenshots en dev**: el cliente next-auth + TypingDemo impiden el "network idle" — verificar por DOM (`preview_eval`) en vez de screenshot.
- **BORA**: sin API — scrape del HTML server-rendered (`/seccion/{seccion}/{yyyymmdd}` + detalle `#cuerpoDetalleAviso`). IDs de 2ª sección alfanuméricos (`A1500779`); los rubros son headers `h5.seccion-rubro` intercalados (se trackean posicionalmente). Los DNU salen como "Decreto": se promueven mirando el texto del detalle (art. 99 inc. 3).
- **Dedup BORA↔InfoLEG**: `reconcile_bora_infoleg` borra la fila BORA cuando llega la gemela InfoLEG, trasplantando antes los `alerta_match` con `notified=true` (anti doble-notificación). Solo LEY/DECRETO/DNU, con guard de instrumento (las Decisiones Administrativas numeran aparte).
- **Orden de beats importa**: `ingest_hcdn_proyectos` (08:00) pisa `norma.estado` a diario; `ingest_hcdn_movimientos` (08:30) lo re-deriva. No invertirlos.
- **Fuentes nuevas**: runbook en `infra/DEPLOY.md` (dry-run → backfill → `match_alertas(notify=False)` → beat). Registry con SLOs en `vigia_shared/sources.py`; estado operativo sin ssh en `GET /health/sources`.
- **BORA 2ª NO entra a `norma`**: va a `aviso_societario` (tabla y FTS propios, router `/avisos`, página "Radar societario") para no contaminar feed/stats/alertas.
- **Plataforma gratuita, sin trial** (desde 2026-07-20): se eliminó el gating por free trial — `require_active_plan` ya no devuelve 402 `trial_expired` (solo exige sesión + membresía) y no hay cartel en el web. Los campos `trial_ends_at`/`VIGIA_TRIAL_DAYS` quedan inertes. **No reintroducir gating por plan/trial sin pedido explícito.** La monetización es aporte voluntario: sección pública `/apoyar` (links de Mercado Pago de la Fundación Colossus Lab + CBU), con `/apoyar/gracias` como back URL de MP.
- **Alertas por-sector**: una alerta es válida con `keywords` **O** `sectores` (422 `criterio_vacio` solo si ambos vacíos). Sin keywords, el matcher filtra solo por `sector = ANY(...)` — sin el filtro FTS. `POST /alerts/preview` estima el volumen (normas de los últimos 30 días) reusando esa misma lógica.
- **`/v1` es contrato con terceros; los routers sin prefijo son del web.** Leen la
  misma tabla y son dos superficies distintas a propósito: `vigia_shared.schemas`
  se mueve cuando el web necesita un campo, y si `/v1` reusara esos modelos un
  ajuste de UI le rompería la integración a otro sin aparecer en el diff. El
  contrato público vive en `routers/v1/schemas.py`: agregar un campo es explícito,
  sacarlo es breaking. **No exponer `raw` ni `search_vector`** (hay un test que lo
  chequea).
- **`updated_since` CAMBIA el orden de `/v1/normas`** — de `fecha_publicacion DESC`
  a `updated_at ASC`. No es un capricho: es la única forma de que la sync
  incremental no se saltee filas (una fila modificada durante el recorrido se
  mueve al final y se vuelve a ver; ordenado por fecha de publicación pasaría lo
  contrario). Por eso **el modo viaja adentro del cursor** y reusar uno del otro
  orden da 400 `cursor_de_otro_orden`.
- **La paginación de `/v1` es keyset, no offset**, con comparación de tupla
  (`(updated_at, id) > (:u0, :i0)`) para que sea condición de arranque del índice
  — índice `ix_norma_updated` (migración 0009). El feed va en **dos tramos**
  (primero con `fecha_publicacion`, después las NULL): un solo recorrido con
  `... OR fecha_publicacion IS NULL` deja de ser tupla pura y Postgres vuelve a
  escanear el índice desde el principio en cada página. `/v1` no devuelve `total`
  (COUNT del corpus filtrado = seq scan de medio millón).
- **`/v1` NO lleva `Cache-Control`** (ver `_CACHEABLE_PREFIXES` en `main.py`): una
  respuesta guardada 120 s en un proxy le hace creer al integrador que no hubo
  novedades. El feed interno sí, porque lo consume un browser.

## Diseño / UX

Tema OpenArg calcado de `../Open Arg/openarg_frontend` (spec: `designNuevaOpenArgTheme.md` ahí):
dark cinematic `#06090F/#0D1117`, celeste `#74ACDF` + sol `#F6B40E`, tints rgba para badges,
franja-bandera, Familjen Grotesk para headlines, JetBrains Mono para datos, FadeIn on-scroll
con `prefers-reduced-motion`. El `<em>` en títulos display va en sol itálica.

## Roadmap pendiente

El roadmap interno (`PLAN.md`) vive solo local, fuera del repo público.
