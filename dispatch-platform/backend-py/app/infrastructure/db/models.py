"""
SQLAlchemy ORM models for this foundation patch: User, Worker, Trade, Task,
WorkerCapability, Assessment — the minimum needed to host the already-
approved capability model (Trade -> Task -> WorkerCapability -> Assessment)
plus the identity rows its foreign keys require.

Column-for-column, this mirrors prisma/schema.prisma's Trade/Task/
WorkerCapability/Assessment blocks and the subset of User/Worker those
depend on. Job/JobOffer/Shift/ShiftEvent/Rating/Notification/Otp and the
Worker counters (trustScore, avgRating, totalShifts, ...) are NOT ported —
they belong to dispatch/trust/shift domains this patch deliberately does not
touch. See docs/PythonMigration.md.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    phone: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    worker: Mapped[WorkerModel | None] = relationship(back_populates="user", uselist=False)


class WorkerModel(Base):
    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    # Legacy CSV skill column — carried over unused. See module docstring.
    legacy_skills_csv: Mapped[str | None] = mapped_column("skills_csv", String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped[UserModel] = relationship(back_populates="worker")
    capabilities: Mapped[list[WorkerCapabilityModel]] = relationship(back_populates="worker")


class TradeModel(Base):
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    tasks: Mapped[list[TaskModel]] = relationship(back_populates="trade")


class TaskModel(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trade_id: Mapped[str] = mapped_column(String(36), ForeignKey("trades.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    safety_qualification_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    adjacency_group: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    trade: Mapped[TradeModel] = relationship(back_populates="tasks")
    capabilities: Mapped[list[WorkerCapabilityModel]] = relationship(back_populates="task")


class WorkerCapabilityModel(Base):
    __tablename__ = "worker_capabilities"
    __table_args__ = (UniqueConstraint("worker_id", "task_id", name="uq_worker_capability_worker_task"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    worker_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workers.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    provenance: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    restrictions: Mapped[str | None] = mapped_column(String(500))
    evidence_ref: Mapped[str | None] = mapped_column(String(500))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    worker: Mapped[WorkerModel] = relationship(back_populates="capabilities")
    task: Mapped[TaskModel] = relationship(back_populates="capabilities")
    assessments: Mapped[list[AssessmentModel]] = relationship(
        back_populates="worker_capability", cascade="all, delete-orphan"
    )


class AssessmentModel(Base):
    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    worker_capability_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("worker_capabilities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[str] = mapped_column(String(500), nullable=False)
    assessed_by: Mapped[str | None] = mapped_column(String(36))
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    evidence_notes: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    worker_capability: Mapped[WorkerCapabilityModel] = relationship(back_populates="assessments")
