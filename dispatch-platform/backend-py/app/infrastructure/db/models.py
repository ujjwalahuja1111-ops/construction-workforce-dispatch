"""
SQLAlchemy ORM models: User, Worker, Trade, Task, WorkerCapability,
Assessment (the capability foundation), plus WorkRequirement,
CrewRequirement, WorkerSafetyQualification (the work-requirement /
dispatch-candidate slice — see docs/WorkRequirement.md).

Column-for-column, the capability foundation mirrors prisma/schema.prisma's
Trade/Task/WorkerCapability/Assessment blocks and the subset of User/Worker
those depend on. Job/JobOffer/Shift/ShiftEvent/Rating/Notification/Otp,
Project/Contractor-as-its-own-table, and the Worker trust counters
(trustScore, avgRating, totalShifts, ...) are NOT ported — they belong to
the legacy dispatch/trust/shift domains this backend deliberately does not
touch yet; a "contractor" here is just a User with role CONTRACTOR, same as
the TS backend's auth layer already treats it before Contractor-profile
fields (companyName, gstNumber, ...) come into play. See
docs/PythonMigration.md.

`Worker.is_available` is a new column, ported from the TS `Worker.isAvailable`
field (prisma/schema.prisma) — additive, defaults `True` — needed because
candidate matching (see app/services/matching_service.py) must be able to
exclude an unavailable worker, and nothing before this patch read or wrote
it on the Python side.
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
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped[UserModel] = relationship(back_populates="worker")
    capabilities: Mapped[list[WorkerCapabilityModel]] = relationship(back_populates="worker")
    safety_qualifications: Mapped[list[WorkerSafetyQualificationModel]] = relationship(
        back_populates="worker"
    )


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
    safety_qualifications: Mapped[list[WorkerSafetyQualificationModel]] = relationship(back_populates="task")


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


# -----------------------------------------------------------------------------
# WORK REQUIREMENT / CREW REQUIREMENT — the client-request -> dispatch-
# candidate slice. See docs/WorkRequirement.md for the model writeup.
# -----------------------------------------------------------------------------


class WorkRequirementModel(Base):
    __tablename__ = "work_requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # The requesting contractor is a User (role CONTRACTOR) — see module
    # docstring. Not a Contractor-profile FK; that table doesn't exist here.
    contractor_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    requested_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    lines: Mapped[list[CrewRequirementModel]] = relationship(
        back_populates="work_requirement",
        cascade="all, delete-orphan",
        order_by="CrewRequirementModel.created_at",
    )


class CrewRequirementModel(Base):
    """One line within a WorkRequirement: N workers of a given task at a
    minimum capability level, e.g. "1 x BRICKWORK_NEW_WALL, level 3+"."""

    __tablename__ = "crew_requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    work_requirement_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("work_requirements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Restrict, not Cascade — same convention as WorkerCapability.task: a
    # Task referenced by a CrewRequirement must be deactivated, never
    # hard-deleted.
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    min_level: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    # A snapshot at creation time (see classification_service.py) — not
    # re-derived from Task on every read, so a later change to a Task's own
    # default doesn't silently rewrite an already-placed requirement.
    safety_qualification_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    work_requirement: Mapped[WorkRequirementModel] = relationship(back_populates="lines")
    task: Mapped[TaskModel] = relationship()


class WorkerSafetyQualificationModel(Base):
    """A worker holding a safety qualification for a specific task. Minimal
    on purpose: no qualification taxonomy, no expiry, no issuing-body model
    — a worker either holds the task's qualification or doesn't. See
    docs/WorkRequirement.md "Safety qualification gate" for why this is
    scoped to (worker, task) rather than a separate qualification code."""

    __tablename__ = "worker_safety_qualifications"
    __table_args__ = (
        UniqueConstraint("worker_id", "task_id", name="uq_worker_safety_qualification_worker_task"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    worker_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workers.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    worker: Mapped[WorkerModel] = relationship(back_populates="safety_qualifications")
    task: Mapped[TaskModel] = relationship(back_populates="safety_qualifications")
