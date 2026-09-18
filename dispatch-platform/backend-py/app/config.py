"""
Application settings, loaded from environment / .env.

Naming mirrors the existing TypeScript backend's config/env.ts wherever the
concept is the same (DATABASE_URL, JWT_SECRET, JWT_EXPIRES_IN, API_PREFIX,
CORS_ORIGIN, PORT) — this is a *different* .env file (backend-py/.env, not
backend/.env), so there is no collision, but reusing the names keeps the two
services conceptually aligned during the migration.

One deliberate difference: DATABASE_URL here is a SQLAlchemy-style URL
(`sqlite:///./dev.db`, `postgresql+psycopg://user:pass@host/db`), not a
Prisma-style one (`file:./dev.db`) — the two backends do not share a
DATABASE_URL value even though the variable name matches.

JWT_SECRET *should* be set to the same value as the TypeScript backend's
during the migration window, so a token issued by either service verifies on
the other — see docs/PythonMigration.md.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    node_env: str = "development"
    port: int = 8003  # distinct from the TS backend's default 8002 so both can run side by side
    api_prefix: str = "/api"

    database_url: str = "sqlite:///./dev.db"

    jwt_secret: str = "replace-with-a-long-random-local-dev-secret"
    jwt_expires_in_days: int = 30
    jwt_algorithm: str = "HS256"

    cors_origin: str = "*"


@lru_cache
def get_settings() -> Settings:
    return Settings()
