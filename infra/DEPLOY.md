# Deploy de Vigía — Runbook (Fase 4)

> **Deploy real (2026-06):** EC2 all-in-one (t3.small, us-east-1)
> con perfil `local-data` del compose. API en `https://vigia-api.openarg.org`,
> web en `https://vigia.openarg.org` (Vercel). User-data en `infra/ec2-user-data.sh`.
> Orden de arranque all-in-one (el `pull` evita que compose buildee en el EC2):
> ```bash
> docker compose -f docker-compose.prod.yml --profile local-data pull
> docker compose -f docker-compose.prod.yml --profile local-data up -d db redis
> docker compose -f docker-compose.prod.yml run --rm --no-deps migrate
> docker compose -f docker-compose.prod.yml up -d --no-build api worker worker-beat caddy
> ```

Arquitectura de producción (patrón Laboratorio Colossus):

```
                 ┌─────────────┐
   navegador ───▶│   Vercel    │  apps/web (Next.js 16)
                 └──────┬──────┘
                        │ HTTPS (NEXT_PUBLIC_API_URL)
                 ┌──────▼───────────────────────────┐
                 │ EC2  ·  docker compose            │
                 │  Caddy (TLS) ─▶ api (FastAPI)     │
                 │                worker + beat       │
                 └───────┬───────────────┬───────────┘
                         │               │
                   ┌─────▼─────┐   ┌──────▼──────┐
                   │ RDS PG16  │   │ ElastiCache │
                   │ +pgvector │   │   Redis     │
                   └───────────┘   └─────────────┘
```

- **Web** → Vercel (root `apps/web`).
- **Backend** (api + workers + beat) → EC2 con `docker-compose.prod.yml` + Caddy.
- **DB** → RDS Postgres 16 (pgvector). **Cache/broker** → ElastiCache Redis.
- Imágenes → GHCR (`ghcr.io/colossus-lab/vigia-{api,workers}`), via CI.

## Cuenta AWS

- Account `<AWS_ACCOUNT_ID>`, IAM user `<IAM_USER>` (AWS CLI v2 ya autenticado en el equipo).
- Verificar: `aws sts get-caller-identity`.
- Región sugerida: `us-east-1` (igual que el resto del lab / Bedrock).

---

## A. Aprovisionar infraestructura (una vez)

> Reemplazar `<...>`. Anotar los endpoints que devuelve cada comando.

### A.1 RDS Postgres 16 + pgvector
```bash
aws rds create-db-instance \
  --db-instance-identifier vigia-db \
  --engine postgres --engine-version 16 \
  --db-instance-class db.t4g.micro \
  --allocated-storage 20 --storage-type gp3 \
  --master-username vigia --master-user-password '<DB_PASS>' \
  --db-name vigia --backup-retention-period 7 \
  --vpc-security-group-ids <SG_DB> --no-publicly-accessible
```
Tras crearse, conectarse una vez y habilitar extensiones (las migra 0001 igual,
pero conviene dejarlas listas):
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
```

### A.2 ElastiCache Redis 7
```bash
aws elasticache create-cache-cluster \
  --cache-cluster-id vigia-redis \
  --engine redis --cache-node-type cache.t4g.micro \
  --num-cache-nodes 1 --security-group-ids <SG_REDIS>
```

### A.3 EC2 (backend host)
- AMI Amazon Linux 2023, `t3.small` (2 vCPU / 2 GB), 20 GB gp3.
- Security group: inbound 80/443 (mundo), 22 (tu IP). Outbound all.
- Instalar Docker + compose plugin:
  ```bash
  sudo dnf install -y docker && sudo systemctl enable --now docker
  sudo usermod -aG docker ec2-user
  # compose plugin
  sudo dnf install -y docker-compose-plugin || \
    (sudo mkdir -p /usr/local/lib/docker/cli-plugins && \
     sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
       -o /usr/local/lib/docker/cli-plugins/docker-compose && \
     sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose)
  ```
- Los SG de RDS y Redis deben permitir ingreso desde el SG del EC2 (5432 / 6379).

### A.4 Secrets (recomendado)
Guardar `AUTH_SECRET`, `AUTH_GOOGLE_*`, `RESEND_API_KEY`, `DATABASE_URL`,
`REDIS_URL` en AWS Secrets Manager y volcarlos a `.env.production` en el deploy:
```bash
aws secretsmanager create-secret --name vigia/prod --secret-string file://.env.production.json
```

---

## B. Construir y publicar imágenes

**Vía CI (recomendado):** push a `main` dispara `.github/workflows/build-images.yml`
→ publica `vigia-api` y `vigia-workers` a GHCR. Requiere que el repo tenga
permisos de packages (automático con `GITHUB_TOKEN`).

**Manual (desde el equipo):**
```bash
echo $GHCR_TOKEN | docker login ghcr.io -u <user> --password-stdin
docker build -t ghcr.io/colossus-lab/vigia-api:latest     -f apps/api/Dockerfile .
docker build -t ghcr.io/colossus-lab/vigia-workers:latest -f apps/workers/Dockerfile .
docker push ghcr.io/colossus-lab/vigia-api:latest
docker push ghcr.io/colossus-lab/vigia-workers:latest
```

---

## C. Desplegar el backend en EC2

```bash
# en el EC2
git clone https://github.com/colossus-lab/vigia.git && cd vigia
cp .env.production.example .env.production    # completar con los endpoints de A
docker login ghcr.io                          # si las imágenes son privadas

# levantar (RDS + ElastiCache externos). El servicio `migrate` aplica Alembic.
docker compose -f docker-compose.prod.yml up -d

# EC2 all-in-one (sin RDS/ElastiCache): agregar el perfil local-data
# docker compose -f docker-compose.prod.yml --profile local-data up -d
```

`migrate` corre `alembic upgrade head` antes de la API. Para cargar datos
iniciales (InfoLEG):
```bash
docker compose -f docker-compose.prod.yml run --rm worker \
  python -c "from vigia_workers.tasks import ingest_infoleg_full as t; print(t())"
```

### Caddy + DNS
- Apuntar `api.vigia.legal` (A record) a la IP elástica del EC2.
- `infra/caddy/Caddyfile` ya hace `reverse_proxy api:8000` con TLS automático
  (Let's Encrypt). Editar el dominio si difiere.

---

## D. Desplegar el web en Vercel

1. https://vercel.com/new → importar `colossus-lab/vigia`.
2. **Root Directory** → `apps/web`. Framework: Next.js. Install: `pnpm install`. Build: `pnpm build`.
3. Env vars en Vercel:
   ```
   NEXT_PUBLIC_API_URL=https://api.vigia.legal
   INTERNAL_API_URL=https://api.vigia.legal
   NEXT_PUBLIC_AUTH_ENABLED=true
   AUTH_ENABLED=true
   AUTH_SECRET=<mismo que el backend>
   AUTH_GOOGLE_ID=<google client id>
   AUTH_GOOGLE_SECRET=<google client secret>
   ```
4. Dominio: `vigia.legal` / `www.vigia.legal` (debe coincidir con `API_CORS_ORIGINS` del backend).

## E. Google OAuth

En Google Cloud Console → OAuth client (Web):
- Authorized origin: `https://vigia.legal`
- Redirect URI: `https://vigia.legal/api/auth/callback/google`

---

## F. Verificación post-deploy

```bash
curl https://api.vigia.legal/health                 # {"status":"ok"}
curl https://api.vigia.legal/health/detailed         # conteo de normas + fuentes
curl "https://api.vigia.legal/normas?limit=1"        # datos reales
```
- Web: abrir `https://vigia.legal/feed` → normas reales; login Google → onboarding.
- Crear una alerta → `match_alertas` corre por beat (o `docker compose ... run --rm worker python -c "from vigia_workers.alerts import match_alertas as t; print(t())"`) → llega email (si `RESEND_API_KEY`).

## Fuentes de datos: runbook de operación

**Observabilidad sin ssh**: `GET /health/sources` — última corrida, status,
`max_fecha_publicacion` y flag `stale` por fuente (SLOs en
`packages/shared/src/vigia_shared/sources.py`). El beat `check-sources` (cada
6 h) marca `stale` y avisa por email si se define `OPS_ALERT_EMAIL`.

**Dry-run de una ingesta** (fetch + parse + conteos, sin tocar la DB):

```bash
docker compose -f docker-compose.prod.yml run --rm worker \
  python -c "from vigia_workers.tasks import ingest_infoleg as t; print(t(dry_run=True))"
```

**Alta de una fuente nueva** (siempre en este orden):
1. Deploy del código con la task nueva, SIN beat todavía.
2. Dry-run en el EC2 → revisar conteos y sample.
3. Backfill real **con `notify=False`**: la task cruza alertas pero NO manda mails
   (evita spamear a los usuarios con el golpe de normas históricas). Las tasks de
   ingesta notifican inline por default (`notify=True`, correcto para el beat diario).
4. (Opcional, confirmación) `match_alertas(notify=False)` → debería dar `new_matches: 0`.
5. Habilitar el beat (deploy con la entrada en `celery_app.py`).
6. Smoke: `/health/sources` muestra la fuente en `ok` con `max_fecha` razonable.

**Alta concreta — BO CABA (`bocaba`) y BO PBA (`bopba`)**: ambas ya traen task,
beat y registry. En el EC2, por cada una (CABA usa API JSON; PBA baja PDFs ~29 MB/edición):

```bash
# dry-run (CABA / PBA)
docker compose -f docker-compose.prod.yml run --rm worker \
  python -c "from vigia_workers.tasks import ingest_bocaba as t; print(t(dry_run=True))"
docker compose -f docker-compose.prod.yml run --rm worker \
  python -c "from vigia_workers.tasks import ingest_pba as t; print(t(dry_run=True))"
# backfill con notify=False (NO manda mails; subir `dias` para más historia,
# PBA chico por el peso del PDF)
docker compose -f docker-compose.prod.yml run --rm worker \
  python -c "from vigia_workers.tasks import ingest_bocaba as t; print(t(dias=10, notify=False))"
docker compose -f docker-compose.prod.yml run --rm worker \
  python -c "from vigia_workers.tasks import ingest_pba as t; print(t(dias=5, notify=False))"
```

La sección web **Boletines Oficiales** (Nacional/PBA/CABA) consume
`GET /normas/ediciones?source=bocaba|bopba`; las pestañas CABA/PBA muestran datos
recién **después** del backfill (antes: "Sin ediciones"). Gotcha PBA: cert SSL roto
→ el connector va con `verify_ssl=False` (ya seteado).

**Rollback universal de una fuente** (cascade limpia matches y tracking):

```sql
DELETE FROM norma WHERE source_id = (SELECT id FROM source_catalog WHERE code = '<code>');
```

## Créditos y aportes

La plataforma es gratuita: el corpus —feed, búsqueda, detalle, `/v1`— no se mide
ni se corta nunca. Lo único que lleva cupo son **los mails de alerta**: 1 crédito
= 1 mail, 100 por mes y por workspace (`VIGIA_CREDITOS_MES`). Al agotarse, el
matcher deja de mandar el digest pero **los matches se siguen registrando** y se
ven en la app; sale un aviso por mail, una sola vez por período.

El free trial quedó inerte (`VIGIA_TRIAL_DAYS`, `trial_ends_at`): no hay 402 en
ninguna parte.

**Activar el aporte de alguien.** No hay webhook de Mercado Pago: la persona se
suscribe, nos escribe, y se corre el script. Acepta el slug del workspace o el
mail con el que la persona entra a Vigía (que casi nunca es el de MP):

```bash
docker compose -f docker-compose.prod.yml exec -T api   python scripts/aporte.py ana@ministerio.gob.ar --nivel base
```

| Nivel | Qué cambia | Monto en `/apoyar` |
|---|---|---|
| `base` | El cupo se renueva **cada quincena** (el 1 y el 16) en vez de por mes | Colaborador/a $5.000 |
| `pleno` | **Sin cupo**: no se le cuentan créditos | Patrocinador/a $20.000 |

**Suscriptores del tier viejo:** hubo un tier *Adherente* de $3.000
(`mpago.la/2vLd7UV`) que se sacó de la página al pasar a dos niveles. El link
sigue vivo y quienes ya estaban suscriptos **siguen pagando**: a ellos les
corresponde `base`, igual que a Colaborador/a. Si alguien escribe mencionando
ése monto, no es un error.

```bash
python scripts/aporte.py --listar                    # aportes activos y si están vigentes
python scripts/aporte.py <slug> --nivel pleno --hasta 2026-12-31
python scripts/aporte.py <slug> --quitar             # vuelve a 'free'
```

Es idempotente y conserva el `desde` original al renovar o cambiar de nivel. Sin
`--hasta` el aporte no vence. El cambio se ve solo en el web (refetchea
`/workspaces/me`); no requiere re-login.

**Si alguien no puede aportar y necesita cupo**, es el mismo script: `--nivel
pleno`. El acceso no depende de poder pagar, y así lo dice `/apoyar`.

**Ver el consumo real** (para recalibrar el cupo):

```bash
docker compose -f docker-compose.prod.yml exec -T db psql -U vigia vigia -c   "SELECT periodo, count(*) AS workspaces, sum(micros)/10000 AS creditos,
          max(micros)/10000 AS el_mas_pesado
     FROM credito_contador GROUP BY periodo ORDER BY periodo DESC LIMIT 6;"
```

Los contadores de períodos viejos los borra `purge_creditos` (beat, domingo
05:15 ART, conserva 13 períodos).

## Backups de la base (S3)

Dump diario completo a `s3://vigia-backups/vigia-YYYY-MM-DD.sql.gz` (~80 MB),
**06:00 ART (09:00 UTC)** por cron del host (no del contenedor), vía
[`infra/backup-db.sh`](backup-db.sh). Retención: lifecycle de 30 días en el
bucket (público bloqueado, SSE-S3, multiparts incompletos se abortan a los 7 días).

**Modelo de permisos (deliberado):** el EC2 tiene el instance profile
`vigia-ec2` con **solo `s3:PutObject`** sobre el bucket — la caja sube backups
pero no puede listarlos, leerlos ni borrarlos (un compromiso del host no
compromete el historial). Listar/restaurar requiere credenciales admin desde
afuera.

```bash
# cron instalado en el host (crontab de ec2-user; cronie en AL2023):
0 9 * * * /home/ec2-user/vigia/infra/backup-db.sh >> /home/ec2-user/vigia-backup.log 2>&1

# correr un backup manual:
~/vigia/infra/backup-db.sh

# listar backups (desde tu máquina, con credenciales admin):
aws s3 ls s3://vigia-backups/ --human-readable
```

**Restore** (desde tu máquina con credenciales admin; el destino debe ser una
base vacía — para desastre total, recrear `db` con el compose y dejar que
`migrate` NO corra antes del restore):

```bash
aws s3 cp s3://vigia-backups/vigia-YYYY-MM-DD.sql.gz - | gunzip | \
  ssh -i ~/.ssh/<key>.pem ec2-user@<EIP> \
  "docker compose -f ~/vigia/docker-compose.prod.yml exec -T db psql -U vigia -d vigia"
```

Notas: el dump usa `--no-owner` (restaura con cualquier rol); `search_vector`
es columna GENERATED — no viaja en el dump y se regenera sola al insertar.
Verificar que el cron vive: `tail ~/vigia-backup.log` en el EC2.

## Costos aproximados (us-east-1)
EC2 t3.small (~$15) + RDS t4g.micro (~$13) + ElastiCache t4g.micro (~$12) ≈ **$40/mo**.
Web en Vercel: free/pro. Bajar costos: EC2 all-in-one con perfil `local-data` (~$15/mo) hasta tener tráfico.

## Conocidos
- **NextAuth v5-beta ↔ Next 16**: si al activar OAuth real aparece el error de
  `headers()` async, bumpear `next-auth` a la primera versión que soporte Next 16
  nativo (mismo issue documentado en InvestArg).
- Endpoints de datos (`/normas`, `/search`, `/stats`) son públicos a propósito
  (datos legislativos abiertos); el gating aplica a `/workspaces` y `/alerts`.
