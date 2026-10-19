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
apps/api/       FastAPI (vigia_api) — routers: health, normas, search (FTS), stats, auth, workspaces, invitations, alerts, avisos, congreso
apps/web/       Next.js 16 App Router (JSX, no TS) — tema OpenArg dark + paleta Argentina
apps/workers/   Celery (vigia_workers) — tasks de ingesta + matching de alertas + beat schedule
packages/shared/      modelos SQLAlchemy + schemas Pydantic + constantes (vigia_shared)
packages/connectors/  InfoLEG + HCDN (vigia_connectors)
db/alembic/     migraciones (0001 inicial … 0011 créditos, 0012 congreso)
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
- **`resumen_ia` solo se genera una vez por norma**: `ingest_bora_primera` tiene
  `lookback_days=5` y corre 2 veces por día, así que sin filtro cada aviso se le
  mandaba al modelo ~10 veces (medido: 297 llamadas para 58 normas nuevas). El
  `COALESCE` del upsert protege el dato guardado pero la llamada ya se pagó — por
  eso `_ya_resumidas()` saltea los que ya tienen resumen antes de llamar. El
  detalle HTML **sí** se sigue bajando: hace falta para detectar el DNU y para el
  resumen del feed.
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
- **El listado del BORA corta en 100 avisos por sección y fecha** (el resto
  entra por scroll infinito), así que `fetch_seccion` ingiere ediciones
  incompletas sin que nada falle. Medido 2026-09-10 recorriendo la paginación:
  1ª del 08/09 → 124 reales / 100 ingeridos; 1ª del 01/09 → 129/100; **2ª del
  09/09 → 468 reales / 100 ingeridos (falta 78%)**. La 1ª solo pega el tope en
  ediciones pesadas (2 de las últimas 31); la **2ª lo pega todos los días
  hábiles** — por eso `avisos/stats` da números redondos (100/día exactos).
  Todavía no está resuelto, pero **ya no es silencioso**: `listado_truncado()`
  marca la fuente en `warn` diciendo qué ediciones quedaron cortadas.
- **Para paginar el listado del BORA**: GET
  `/seccion/actualizar/{seccion}?pag=N&ult_rubro=...` con la cookie de sesión
  que deja el GET del listado (la fecha **no** va en la query: sale de la
  sesión). Devuelve `{html, hay_mas_datos, sig_pag, ult_rubro}`; se itera
  mientras `hay_mas_datos` arrastrando `ult_rubro`, que arranca en la var JS
  `ultimoRubro` del listado — hace falta porque los rubros son headers
  posicionales. **No medir la completitud probando IDs correlativos**:
  `/detalleAviso/{s}/{id}/{fecha}` ignora la fecha de la URL y devuelve el aviso
  igual, así que los IDs no dicen nada sobre cuántos avisos tuvo un día (así se
  sobreestimó el faltante de la 1ª en ~60% cuando es ~20%).
- **`warn` no es `stale`, y ahora se ve**: los guards de ingesta escriben
  `last_status='warn'` para cosas ciertas pero permanentes (el tope de 100 pasa
  todos los días en la 2ª sección). Meterlas en `stale` dejaría la fuente en rojo
  fijo y nadie volvería a mirar el endpoint, así que `/health/sources` las
  expone en un campo `warnings` aparte y `stale` sigue significando lo mismo.
  Ojo con el bug que esto arregla: `_stale_reasons` solo mostraba `last_error`
  para `error`/`stale`, así que el guard de "0 avisos en día hábil" venía
  guardando su motivo **sin mostrarlo en ningún lado** desde que se escribió.
  `warn` tampoco manda mail: `freshness.py` solo escala `error`.
- **Dedup BORA↔InfoLEG**: `reconcile_bora_infoleg` borra la fila BORA cuando llega la gemela InfoLEG, trasplantando antes los `alerta_match` con `notified=true` (anti doble-notificación). Solo LEY/DECRETO/DNU, con guard de instrumento (las Decisiones Administrativas numeran aparte).
- **Orden de beats importa**: `ingest_hcdn_proyectos` (08:00) pisa `norma.estado` a diario; `ingest_hcdn_movimientos` (08:30) lo re-deriva. No invertirlos.
- **Fuentes nuevas**: runbook en `infra/DEPLOY.md` (dry-run → backfill → `match_alertas(notify=False)` → beat). Registry con SLOs en `vigia_shared/sources.py`; estado operativo sin ssh en `GET /health/sources`.
- **BORA 2ª NO entra a `norma`**: va a `aviso_societario` (tabla y FTS propios, router `/avisos`, página "Radar societario") para no contaminar feed/stats/alertas.
- **Plataforma gratuita, sin trial** (desde 2026-07-20): se eliminó el gating por free trial — `require_active_plan` ya no devuelve 402 `trial_expired` (solo exige sesión + membresía) y no hay cartel en el web. Los campos `trial_ends_at`/`VIGIA_TRIAL_DAYS` quedan inertes. La monetización es aporte voluntario: sección pública `/apoyar` (links de Mercado Pago de la Fundación Colossus Lab + CBU), con `/apoyar/gracias` como back URL de MP.
- **Créditos: lo único medido es el mail de alerta** (desde 2026-08-21, `vigia_shared/creditos.py`,
  migración 0011). El corpus —feed, búsqueda, detalle, `/v1`— **no se mide ni se corta nunca**, y
  `require_active_plan` sigue sin chequear créditos: **no hay 402 en ninguna parte**. Lo que el cupo
  frena es el `send_email` del digest, en `vigia_workers/alerts.py`. Sin cupo el match **igual queda
  registrado** y se ve en la app — se pierde el aviso, nunca el dato.
  - Se guarda **plata** (micro-dólares) y se muestran créditos: 1 crédito = US$0,01 = 1 mail. Cambiar
    el valor del crédito es cambiar una constante, sin backfill.
  - **El período va en la PK de `credito_contador`** (`2026-08`, o `2026-08q1/q2` para el nivel
    `base`, que recarga por quincena). Por eso **no hay job de reset**: al rotar se escribe una fila
    nueva que arranca en cero, y eso cubre gratis el cambio de nivel a mitad de mes. `periodo_de()`
    tiene que dar lo mismo en la API y en el worker o se lee un contador distinto del que se cobra.
  - **El aviso de "sin créditos" sale UNA vez por período**, con la marca `aviso_agotado_at` en esa
    misma fila y un `UPDATE ... WHERE ... IS NULL RETURNING` que gana la carrera. El matcher corre
    cada hora: sin ese candado saldría un mail por hora para avisar que dejamos de mandar mails.
  - Cupo gratis **100/mes** (`VIGIA_CREDITOS_MES`). Calibrado contra prod: de 110 workspaces con
    digests, la mediana consume 18/mes y el máximo 60 — hoy no le corta a nadie, y es a propósito.
  - Niveles `free|base|pleno` en `workspace.plan` + metadatos en `workspace.aporte` (JSONB). Los
    escribe **solo `scripts/aporte.py`**, nunca la web: no hay webhook de Mercado Pago. Dos
    tiers en `/apoyar`: Colaborador/a $5.000 → `base`, Patrocinador/a $20.000 → `pleno`.
  - El saldo viaja *piggyback* en `GET /workspaces/me` — sin endpoint propio y sin tocar la
    allowlist del BFF.
- **Alertas por-sector**: una alerta es válida con `keywords` **O** `sectores` (422 `criterio_vacio` solo si ambos vacíos). Sin keywords, el matcher filtra solo por `sector = ANY(...)` — sin el filtro FTS. `POST /alerts/preview` estima el volumen (normas de los últimos 30 días) reusando esa misma lógica.
- **El matcher mira DOS fechas**: `ingested_at >= anchor_at` (que la norma
  haya entrado después de crear la alerta) **y** `fecha_publicacion` dentro de
  `VENTANA_FECHA_DIAS` (120) o nula. Sin la segunda, una carga histórica
  (backfill, o InfoLEG digitalizando una ley de 1964) entraba "nueva" y
  matcheaba como noticia.
  - Las dos razones de la segunda condición:
    - `notify=False` evita el mail, pero el match queda en la app como si
      fuera de hoy.
    - El match marcado es lo único que impide que el matcher siguiente vuelva
      a encontrar esa norma. Sin la ventana, **borrar matches históricos los
      hace volver, y esa vez con mail**.
  - 120 d sale de la demora fecha→carga medida en prod: p99 de 35 d en
    InfoLEG, 89 d en HCDN (baches del dataset) y ≤ 7 d en los boletines. Si
    entra una fuente con más demora, hay que medirla antes de ajustar.
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
- **`/v1` exige API key; los routers del web NO.** La dependency
  (`limitar_por_apikey`) cuelga del router de `/v1` entero y no de cada endpoint,
  así que sumar uno nuevo no implica acordarse de gatearlo. Con
  `AUTH_ENABLED=false` (dev) `/v1` queda abierto, igual que el resto.
- **`/api-keys` se autentica con la SESIÓN, no con una key** — una key no puede
  emitir ni revocar otra key, así que una filtrada solo sirve para leer `/v1`.
  Alta y revocación piden `require_escritura` (owner|admin): una key da acceso al
  corpus en nombre del workspace y un `viewer` no debería poder acuñarla.
- **Del secreto solo se guarda el SHA-256** y se muestra **una vez**. SHA-256 y no
  bcrypt/argon2 a propósito: es un secreto aleatorio de 256 bits que generamos
  nosotros, no un password — no hay diccionario que atacar y un KDF lento solo
  agregaría latencia a cada request de `/v1`. El índice único sobre `token_hash`
  es lo que hace que verificar sea un lookup.
- **El rate limit de alta de keys (30/h) tiene que quedar por encima de
  `apikey_max_por_workspace` (10)**: si fueran iguales, al llegar al techo saldría
  un 429 genérico y el 409 `limite_de_keys_alcanzado` sería inalcanzable.
- **La cuota diaria vive en memoria y se pierde al reiniciar la API**
  (`_diarios` en `core/ratelimit.py`, contador por día calendario UTC — O(1), no
  una cola de timestamps). Es cuota de cortesía, no facturación. El reset a las
  00:00 UTC viaja en `X-RateLimit-Reset`.
- **La allowlist del BFF no es un proxy genérico a propósito**: sumar un endpoint
  al web implica agregarlo a mano en `app/api/vigia/[...path]/route.js` (un rewrite
  `:path*` ya se removió una vez por dejar un proxy abierto en Vercel). `/api-keys`
  ya está en la allowlist y su UI vive en `app/(app)/settings/api/page.jsx`.
- **Congreso: lo que PASA no entra a `norma`.** Votaciones, sesiones, asuntos
  tratados y agenda de comisiones van en tablas propias (migración 0012), igual
  que `aviso_societario`. El cruce con los proyectos es por **expediente
  canónico** `NNNN-ORIGEN-AAAA` (`vigia_shared/expedientes.py`): `text[]` con GIN
  en las dos puntas y solapamiento `&&`, porque un proyecto tiene un expediente
  **por cámara** (entra por Diputados como `0010-PE-2026` y en el Senado es
  `CD-12/26`). Si una forma nueva no normaliza, el cruce no falla: no encuentra
  nada — por eso cada forma vista en una fuente real va como caso de test.
  `norma.expedientes` lo llenan solo los mappers de proyectos y `upsert_normas`
  lo actualiza solo si el batch lo trae (las demás fuentes no lo vacían).
  Histórico: `backfill_expedientes` (su `sin_expediente` delata formas que el
  normalizador no reconoce).
- **`senado_proyectos` ingiere orígenes S/PE/JGM/OV y busca ORIGEN POR ORIGEN**
  (`expedienteLugar` del buscador). La primera versión filtraba por origen
  *después* de bajar las páginas, y en prod no trajo ni un PE reciente:
  mezclados, los S (~2.000-6.500 por año) llenan las primeras páginas y los del
  Ejecutivo (~50-90 por año) no aparecen nunca. `CD` sigue afuera (ya entra
  por HCDN).
  - Backfill: `ingest_senado_proyectos(anio_desde=2006, origenes=[...],
    notify=False)` recorre año por año (`expedienteNumeroPos`). **Con
    `anio_desde` la task se niega a correr si `notify=True`.**
  - Las páginas fuera de rango vuelven 200 con la tabla vacía: el corte es la
    primera vacía, con un tope duro de 1000.
- **No toda votación del Senado cruza con un proyecto, y no es un bug**:
  - Muchos expedientes PE votados son **acuerdos** (pliegos de ascensos,
    jueces, embajadores), y no proyectos. Su tipo no está en `TIPOS_PROYECTO`.
    Suelen votarse en bloque bajo "Temas Varios Expedientes".
  - ~1.000 actas citan solo la **orden del día**, sin expediente. Cruzarlas
    exige resolver la O.D. contra el expediente
    (`/parlamentario/parlamentaria/ordenDelDiaResultadoLink/{anio}/{n}`).
- **API `/congreso`** (`routers/congreso.py`, contrato en `docs/congreso-api.md`):
  - Es **pública y cacheable** (está en `_CACHEABLE_PREFIXES`). El gating de la
    sección lo hace el web en `proxy.js`. `/congreso/resumen` además se cachea
    300 s en memoria.
  - **"Sin fuente" es `null`, no 0.** `votaciones_30d` y `estadisticas` valen
    `null` cuando la cámara no tiene ninguna votación en la tabla, que hoy es
    Diputados. No está hardcodeado a `D`: si aparece una fuente de voto
    nominal, se prende solo. El web lo muestra como "sin datos".
  - **Los proyectos cruzados se traen en UNA consulta por página**
    (`_proyectos_para` → `asignar_proyectos`). No agregar consultas por ítem.
  - `alineamiento_bloque` descarta los empates del bloque y los monobloques: si
    no, un monobloque da 100% fijo.
  - Las fechas van con offset fijo `-03:00` y sin zoneinfo, porque Windows no
    trae tzdata.
- **Sección web `/congreso`** (`app/(app)/congreso/`, `components/congreso/`,
  `lib/congreso.js` con `pnpm test:congreso`):
  - **El contenido ancho se cuela como ancho intrínseco** a través de los flex
    del layout `(app)` y deja la página más ancha que el celular, aunque el
    elemento tenga `overflow-x-auto`.
    - Pasó con una sub-nav `min-w-max`, con el `ResponsiveContainer` de
      recharts y con un `truncate` dentro de un `flex-1 min-w-0`.
    - Remedio: `[contain:inline-size]` en el contenedor, o `break-words` en vez
      de `truncate`.
    - Diagnóstico: ocultar secciones de a una y medir
      `document.documentElement.scrollWidth`.
  - **Una `fecha` `YYYY-MM-DD` no pasa por `new Date()`**: la toma como
    medianoche UTC y en Argentina queda el día anterior.
  - Las filas de votación y sesión son un `div` clickeable con el título como
    `<Link>`: adentro hay links a los proyectos, y un `<a>` dentro de otro rompe
    la hidratación.
- **Voto nominal de Diputados: `votaciones.hcdn.gob.ar` tiene reCAPTCHA v3 y NO
  se esquiva.** El dataset CKAN `votaciones_nominales` se cortó en feb-2020. Para
  Diputados se usan resultados por expediente (Boletín de Asuntos Tratados); el
  Senado sí tiene voto nominal en HTML (`/votaciones/detalleActa/{id}`).
- **Diputados en CKAN (`congreso_hcdn.py`)**:
  - **La "Composición Actual" no trae ID.** El ID `HCDNnnnn` sale del recurso
    "Diputados" (histórico, una fila por mandato y por bloque) y se cruza por
    apellido + distrito **del mandato vigente**: el distrito cambia entre
    mandatos. Para elegir entre varios CSV del mismo package:
    `resolve_csv_url(package, recurso=...)`.
  - **Las fechas del CSV `sesiones` vienen 2 días antes** que las del sitio y
    del BAT (huele a epoch de Excel). `combinar_sesiones` mide el desfase en
    cada corrida y lo aplica, y la fecha que se guarda es la del sitio.
- **Asamblea Legislativa**: el sitio y la agenda la numeran igual que la 1ª
  reunión (`reunion=1`). Por eso el `external_id` de sesión es
  `{periodo}-{reunion}` o `{periodo}-A{reunion}`.
- **BAT** (`bat.jsp?periodo=&reunion=&sesion=`):
  - Si no hay boletín devuelve 200 con el wrapper vacío. Las asambleas no
    tienen, y las reuniones sin número de sesión van con `sesion=0`.
  - Se corrige después de publicado, así que cada corrida **reemplaza** los
    asuntos de la sesión.
  - `clave` = expediente principal, si no hay `OD-n`, si no hay `#orden`.
- **Agenda de comisiones (las dos cámaras)**:
  - Una reunión suspendida o reprogramada desaparece de la página. Después del
    upsert se borran las **futuras** de los días mostrados que ya no figuran.
    Con la agenda vacía no se borra nada (lo avisa el warn).
  - En Diputados el `reunId` viene en un `<a>` **comentado**, y
    `prosecretaria=secparl` es una sesión de recinto, no una comisión.
  - **Días cubiertos = de hoy al último día que muestra la página**, no solo
    los que tienen reuniones. Si un día tenía una sola reunión y se suspendió,
    desaparece entero de la página, y contando solo los días que figuran esa
    reunión quedaría como fantasma.
  - La agenda del Senado no trae año: lo infiere `inferir_fecha`, con el día
    de la semana como desempate, y cubre el cruce de diciembre a enero.
- **Votaciones del Senado (`congreso_senado.py`)**:
  - **Las actas solo linkean a los senadores EN FUNCIONES.** Los ex senadores
    vienen sin ID: en un acta de 2008, 71 de 72 filas. Se resuelven por
    nombre + provincia + **fecha** contra `ExportarListadoSenadoresHistorico`
    (`IndiceSenadores`). La fecha desempata homónimos de épocas distintas. Si
    no aparecen, entran con `external_id = nom-<hash>` y el voto no se pierde.
  - **Los IDs de acta no son cronológicos**, y un ID inexistente devuelve 200
    con la plantilla vacía. Mismo error que con el BORA: los IDs no dicen
    nada de fechas ni de completitud.
  - **La fecha del acta es la de la sesión, con la hora de la votación.** Una
    votación de las 02:29 queda con el día en que empezó la sesión. Hay
    excepciones con el acta fechada al día siguiente, y por eso
    `_vincular_sesiones` cae a la sesión del día anterior.
  - `POST /votaciones/actas` con `busqueda_actas[anio]` **no** pide CSRF (el
    buscador de proyectos sí).
  - Hay actas con celdas de voto vacías **en el propio sitio** (la 2530 tiene
    62 de 72). Quedan como `otro`: no es un bug del parser.
  - `congreso_sesion.periodo` del Senado queda NULL: las extraordinarias de
    enero y febrero son del período anterior y el sitio no lo dice.
  - El JSON de datos abiertos del Senado puede traer comas colgantes:
    `cargar_json_tolerante`.
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
