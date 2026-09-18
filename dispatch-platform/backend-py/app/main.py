"""
FastAPI application factory — mirrors the shape of the TS backend's
src/server.ts (buildApp()) closely enough to be recognizable: middleware,
API-prefixed router mount, a global error handler, no route wiring here
(that stays in app/api/routes/*).
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import auth, health
from app.config import get_settings
from app.core.errors import AppError


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="dispatch-backend-py", version="0.1.0")

    origins = ["*"] if settings.cors_origin == "*" else [settings.cors_origin]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    api = settings.api_prefix
    app.include_router(health.router, prefix=api)
    app.include_router(auth.router, prefix=api)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"name": "dispatch-backend-py", "version": "0.1.0"}

    return app


app = create_app()
