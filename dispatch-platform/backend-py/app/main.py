"""
FastAPI application factory — mirrors the shape of the TS backend's
src/server.ts (buildApp()) closely enough to be recognizable: middleware,
API-prefixed router mount, a global error handler, no route wiring here
(that stays in app/api/routes/*).
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import auth, health, worker_capabilities
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

    @app.exception_handler(RequestValidationError)
    def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default for a body/path/query validation failure is 422;
        # the TS contract (and the Zod-based validation it mirrors) treats
        # the same failures — an out-of-range `level`, a malformed `taskId`
        # — as 400 BAD_REQUEST. Re-shaped here, once, so every route gets
        # contract-accurate status codes without repeating this per handler.
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Invalid request",
                    # jsonable_encoder because a validator's raised ValueError
                    # (e.g. our level-range check) lands in errors()[i]["ctx"]
                    # as a live exception instance, which json.dumps can't
                    # serialize on its own.
                    "details": jsonable_encoder(exc.errors()),
                }
            },
        )

    api = settings.api_prefix
    app.include_router(health.router, prefix=api)
    app.include_router(auth.router, prefix=api)
    app.include_router(worker_capabilities.router, prefix=api)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"name": "dispatch-backend-py", "version": "0.1.0"}

    return app


app = create_app()
