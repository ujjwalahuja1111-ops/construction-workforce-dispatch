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
    DispatchOffer,
    DispatchPosition,
    NewCrewRequirementLine,
    Shift,
    Task,
    Trade,
    Worker,
    WorkerCapability,
    WorkerSafetyQualification,
    WorkRequirement,
)
from app.domain.enums import OfferStatus, PositionStatus, ShiftStatus
from app.domain.views import EligibleWorkerView, MyDispatchOfferView, WorkerCapabilityView


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
    def get_by_id(self, crew_requirement_id: str) -> CrewRequirement | None: ...


class DispatchPositionRepository(Protocol):
    def create_many_for_line(
        self, *, work_requirement_id: str, crew_requirement_id: str, quantity: int
    ) -> list[DispatchPosition]: ...
    def list_for_work_requirement(self, work_requirement_id: str) -> list[DispatchPosition]: ...
    def list_for_crew_requirement(self, crew_requirement_id: str) -> list[DispatchPosition]: ...
    def get_by_id(self, position_id: str) -> DispatchPosition | None: ...
    def try_transition(
        self,
        position_id: str,
        *,
        expected_status: PositionStatus,
        new_status: PositionStatus,
        worker_id: str | None,
    ) -> bool: ...
    def committed_worker_ids_on_date(
        self, *, on_date: datetime, exclude_work_requirement_id: str
    ) -> set[str]: ...


class DispatchOfferRepository(Protocol):
    def create(self, *, position_id: str, worker_id: str, expires_at: datetime) -> DispatchOffer: ...
    def get_by_id(self, offer_id: str) -> DispatchOffer | None: ...
    def try_transition(
        self,
        offer_id: str,
        *,
        expected_status: OfferStatus,
        new_status: OfferStatus,
        responded_at: datetime | None,
    ) -> bool: ...
    def cancel_other_pending_for_position(
        self, position_id: str, *, except_offer_id: str, responded_at: datetime
    ) -> list[DispatchOffer]: ...
    def pending_worker_ids_for_work_requirement(
        self, work_requirement_id: str, *, now: datetime
    ) -> set[str]: ...
    def pending_worker_ids_on_date(
        self, *, on_date: datetime, exclude_work_requirement_id: str, now: datetime
    ) -> set[str]: ...
    def previously_declined_or_expired_worker_ids(self, position_id: str) -> set[str]: ...
    def list_expired_pending(self, *, now: datetime) -> list[DispatchOffer]: ...
    def count_pending_for_positions(self, position_ids: list[str]) -> int: ...
    def list_for_position(self, position_id: str) -> list[DispatchOffer]: ...
    def list_for_worker(self, worker_id: str) -> list[MyDispatchOfferView]: ...


class ShiftRepository(Protocol):
    def create(
        self, *, dispatch_position_id: str, worker_id: str, scheduled_for: datetime | None
    ) -> Shift: ...
    def get_by_id(self, shift_id: str) -> Shift | None: ...
    def get_by_dispatch_position_id(self, dispatch_position_id: str) -> Shift | None: ...
    def try_transition(
        self,
        shift_id: str,
        *,
        expected_status: ShiftStatus,
        new_status: ShiftStatus,
        check_in_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> bool: ...


__all__ = [
    "TradeRepository",
    "TaskRepository",
    "WorkerRepository",
    "WorkerCapabilityRepository",
    "WorkerSafetyQualificationRepository",
    "WorkRequirementRepository",
    "CrewRequirementRepository",
    "DispatchPositionRepository",
    "DispatchOfferRepository",
    "ShiftRepository",
]
