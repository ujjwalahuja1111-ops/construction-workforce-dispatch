"""
Framework-free domain entities — plain dataclasses, no SQLAlchemy, no
Pydantic/FastAPI. Business rules operate on these, not on ORM rows or API
schemas, so the domain layer stays independent of both the persistence
mechanism and the transport format (clean-architecture "domain" layer).

Only the entities the approved capability model needs, plus the minimal
User/Worker identity the foreign keys require. Job/Shift/Rating/Crew/
WorkRequirement/DispatchEngine are deliberately not represented here yet —
see docs/PythonMigration.md for what this foundation patch does and does
not include.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import AssessmentType, CapabilityProvenance, Role


@dataclass(slots=True)
class User:
    id: str
    phone: str
    role: Role
    full_name: str
    is_verified: bool
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class Worker:
    id: str
    user_id: str
    city: str | None
    state: str | None
    # Legacy flat-skill CSV, carried over unused — see docs/PythonMigration.md.
    # Nothing in this backend reads or writes it; it exists only so a Worker
    # row created here stays shape-compatible with the TS Worker row it
    # mirrors during the migration window.
    legacy_skills_csv: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class Trade:
    id: str
    code: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class Task:
    id: str
    trade_id: str
    code: str
    name: str
    description: str | None
    safety_qualification_required: bool
    adjacency_group: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class WorkerCapability:
    id: str
    worker_id: str
    task_id: str
    level: int
    provenance: CapabilityProvenance
    confidence: float | None
    restrictions: str | None
    evidence_ref: str | None
    last_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class Assessment:
    id: str
    worker_capability_id: str
    type: AssessmentType
    result: str
    assessed_by: str | None
    assessed_at: datetime
    evidence_notes: str | None
    created_at: datetime
