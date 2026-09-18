"""
Engine/session factory. PostgreSQL-ready: `create_engine` just takes
whatever `DATABASE_URL` resolves to (postgresql+psycopg://... in real
environments, sqlite:///... for local dev/test) — nothing in the app layer
is SQLite- or Postgres-specific.
"""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings


def make_engine(settings: Settings) -> Engine:
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, connect_args=connect_args, future=True)


_engine = make_engine(get_settings())
SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed. Rolls
    back on any exception so a failure mid-write (e.g. an AppError raised
    after a partial flush) never leaves an open transaction dangling."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
