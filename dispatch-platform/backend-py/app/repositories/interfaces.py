"""
Repository interfaces (structural typing via Protocol). Services/routes
depend on these, never on SQLAlchemy directly — the concrete implementation
in sqlalchemy_repositories.py is an infrastructure detail that can be swapped
(e.g. for a test double) without touching anything above this layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.entities import (
    CrewRequirement,
    NewCrewRequirementLine,
    Task,
    Trade,
    Worker,
    WorkerCapability,
    WorkerSafetyQualification,
    WorkRequirement,
)
from app.domain.views import EligibleWorkerView, WorkerCapabilityView


class TradeRepository(Protocol):
    def list_active(self) -> list[Trade]: ...
    def get_by_code(self, code: str) -> Trade | None: ...
    def get_by_id(self, trade_id: str) -> Trade | None: ...


class TaskRepository(Protocol):
    def get_by_code(self, code: str) -> Task | None: ...
    def get_by_id(self, task_id: str) -> Task | None: ...
    def list_by_trade(self, trade_id: str) -> list[Task]: ...


class WorkerRepository(Protocol):
    def get_by_user_id(self, user_id: str) -> Worker | None: ...


class WorkerCapabilityRepository(Protocol):
    def list_for_worker(self, worker_id: str) -> list[WorkerCapability]: ...
    def get_by_worker_and_task(self, worker_id: str, task_id: str) -> WorkerCapability | None: ...
    def create_self_declared(self, worker_id: str, task_id: str, level: int) -> WorkerCapabilityView: ...
    def update_level_self_declared(
        self, capability_id: str, old_level: int, new_level: int
    ) -> WorkerCapabilityView: ...
    def get_view_by_worker_and_task(self, worker_id: str, task_id: str) -> WorkerCapabilityView | None: ...
    def list_views_for_worker(self, worker_id: str) -> list[WorkerCapabilityView]: ...
    def list_capable_workers(self, task_id: str, min_level: int) -> list[EligibleWorkerView]: ...


class WorkerSafetyQualificationRepository(Protocol):
    def has_qualification(self, worker_id: str, task_id: str) -> bool: ...
    def grant(self, worker_id: str, task_id: str) -> WorkerSafetyQualification: ...


class WorkRequirementRepository(Protocol):
    def create(
        self,
        *,
        contractor_user_id: str,
        city: str | None,
        state: str | None,
        requested_for: datetime | None,
        notes: str | None,
    ) -> WorkRequirement: ...
    def get_by_id(self, work_requirement_id: str) -> WorkRequirement | None: ...


class CrewRequirementRepository(Protocol):
    def create_many(
        self, work_requirement_id: str, lines: list[NewCrewRequirementLine]
    ) -> list[CrewRequirement]: ...
    def list_for_work_requirement(self, work_requirement_id: str) -> list[CrewRequirement]: ...


__all__ = [
    "TradeRepository",
    "TaskRepository",
    "WorkerRepository",
    "WorkerCapabilityRepository",
    "WorkerSafetyQualificationRepository",
    "WorkRequirementRepository",
    "CrewRequirementRepository",
]
