"""
Test infrastructure: an isolated in-memory SQLite database per test
(StaticPool keeps the single :memory: connection alive across the whole
test's session use), Base.metadata.create_all instead of running Alembic
(deterministic, no filesystem, no migration-ordering coupling), and a
FastAPI TestClient wired to that same session via dependency override.

Never touches dev.db, never touches a real/production database.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.config import Settings, get_settings
from app.infrastructure.db import models  # noqa: F401  (register tables on Base.metadata)
from app.infrastructure.db.base import Base
from app.main import create_app


@pytest.fixture()
def test_settings() -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        jwt_secret="test-only-jwt-secret-do-not-use-in-prod",
    )


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session: Session, test_settings: Settings) -> Generator[TestClient, None, None]:
    app = create_app()

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_settings] = lambda: test_settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
