FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY packages ./packages
COPY apps/api ./apps/api
COPY db ./db

RUN uv pip install --system -e ./packages/shared -e ./packages/connectors -e ./apps/api

EXPOSE 8000
# --no-proxy-headers: que uvicorn NO reescriba request.client desde los headers
# de proxy. La IP del cliente se decide en un solo lugar, `core.ratelimit.client_ip`,
# leyendo el X-Forwarded-For que sanitiza Caddy. Sin este flag el comportamiento
# depende del default de la versión de uvicorn que haya resuelto el build, y la
# dependencia está declarada como ">=0.30" sin lockfile.
#
# Sin --workers a propósito: los contadores del rate limiter y el cache de
# core/cache.py viven en memoria del proceso. Agregar workers multiplica el
# límite efectivo por N — antes de hacerlo, mover ambos a un store compartido.
CMD ["uvicorn", "vigia_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
