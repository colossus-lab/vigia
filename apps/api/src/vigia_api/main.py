from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vigia_api.core.settings import get_settings
from vigia_api.routers import (
    account,
    alerts,
    auth,
    avisos,
    health,
    invitations,
    normas,
    search,
    stats,
    workspaces,
)

# Sentry — no-op si falta SENTRY_DSN.
_sentry_dsn = os.environ.get("SENTRY_DSN")
if _sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=_sentry_dsn,
            integrations=[StarletteIntegration(), FastApiIntegration()],
            traces_sample_rate=0.1,
            environment=os.environ.get("VIGIA_ENV", "dev"),
        )
    except Exception as exc:  # pragma: no cover
        print(f"[sentry] init failed: {exc!r}")


# Prefijos de datos públicos (CLAUDE.md: los endpoints de datos son públicos
# SIEMPRE; el gating aplica solo a /workspaces, /invitations, /alerts, /account).
# Solo estos llevan Cache-Control: nada con sesión se cachea.
_CACHEABLE_PREFIXES = ("/normas", "/stats", "/avisos", "/search")
_CACHE_CONTROL = "public, max-age=120, stale-while-revalidate=600"


def create_app() -> FastAPI:
    settings = get_settings()
    # Con vigia_docs=False (default) los tres endpoints quedan en 404: FastAPI no
    # registra las rutas cuando las URLs son None. Ver Settings.vigia_docs.
    docs = settings.vigia_docs
    app = FastAPI(
        title="Vigía API",
        version="0.1.0",
        description="Backend de Vigía — inteligencia legislativa y regulatoria argentina.",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    @app.middleware("http")
    async def cache_public_reads(request, call_next):
        """Deja que el browser reuse las lecturas públicas por un rato.

        Las páginas del web son 'use client', así que pegan directo contra la
        API: sin este header cada navegación re-consulta todo. Se limita a GET
        200 sin Authorization para no cachear jamás una respuesta con sesión.
        """
        response = await call_next(request)
        if (
            request.method == "GET"
            and response.status_code == 200
            and "authorization" not in request.headers
            and request.url.path.startswith(_CACHEABLE_PREFIXES)
        ):
            response.headers["Cache-Control"] = _CACHE_CONTROL
        return response

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(workspaces.router)
    app.include_router(account.router)
    app.include_router(invitations.router)
    app.include_router(alerts.router)
    app.include_router(normas.router)
    app.include_router(search.router)
    app.include_router(stats.router)
    app.include_router(avisos.router)
    return app


app = create_app()
