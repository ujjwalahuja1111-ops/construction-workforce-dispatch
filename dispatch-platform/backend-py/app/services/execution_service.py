"""
COMMITTED POSITION -> MINIMAL SHIFT / EXECUTION — the vertical slice that
turns a COMMITTED DispatchPosition into an actual work assignment a worker
can check into, work, and complete. See docs/Execution.md for the full
writeup; this module's docstring covers just the shape of what each method
does.

    COMMITTED DispatchPosition (existing, unchanged, never re-derived here)
        -> CREATE EXECUTION (CONTRACTOR-owner or ADMIN; idempotent)
        -> WORKER CHECKS IN  -> SCHEDULED -> CHECKED_IN
        -> WORKER STARTS     -> CHECKED_IN -> WORKING
        -> WORKER COMPLETES  -> WORKING -> COMPLETED

Dispatch and execution stay cleanly separated boundaries: execution is
never created as a side effect of `DispatchService.accept_offer` — a
contractor/admin explicitly asks for it via
`POST /api/dispatch-positions/{id}/execution`, after which the record is
worker-owned for check-in/start/complete. `DispatchPosition`'s own status
is never mutated by this module; COMMITTED already means "the position is
resolved" from dispatch's point of view, and this module only ever reads
it, never writes it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.entities import DispatchPosition, Shift
from app.domain.enums import PositionStatus, Role, ShiftStatus
from app.domain.views import ShiftView
from app.repositories.sqlalchemy_repositories import (
    SqlAlchemyDispatchPositionRepository,
    SqlAlchemyShiftRepository,
    SqlAlchemyWorkerRepository,
    SqlAlchemyWorkRequirementRepository,
)
from app.services import execution_state_machine


def _utc_now() -> datetime:
    """See app/services/dispatch_service._utc_now for the full rationale
    (SQLite reads every `DateTime(timezone=True)` column back as
    tz-naive) — used here for the same reason, so a stored `check_in_at`/
    `completed_at` never needs re-normalizing before a later comparison."""
    return datetime.now(UTC).replace(tzinfo=None)


class ExecutionService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._work_requirements = SqlAlchemyWorkRequirementRepository(db)
        self._positions = SqlAlchemyDispatchPositionRepository(db)
        self._workers = SqlAlchemyWorkerRepository(db)
        self._shifts = SqlAlchemyShiftRepository(db)

    # ------------------------------------------------------------------
    # POST /api/dispatch-positions/{position_id}/execution
    # ------------------------------------------------------------------

    def create_execution(
        self, dispatch_position_id: str, *, requesting_user_id: str, requesting_role: str
    ) -> tuple[ShiftView, bool]:
        """Returns (view, created) — `created` is False when an execution
        already existed and was returned as-is (idempotent creation; see
        docs/Execution.md "Hard invariant")."""
        position = self._positions.get_by_id(dispatch_position_id)
        if position is None:
            raise AppError.not_found("Dispatch position not found")

        work_requirement = self._work_requirements.get_by_id(position.work_requirement_id)
        assert work_requirement is not None
        if requesting_role != Role.ADMIN and work_requirement.contractor_user_id != requesting_user_id:
            raise AppError.forbidden("You may only create execution for your own work requirements")

        existing = self._shifts.get_by_dispatch_position_id(dispatch_position_id)
        if existing is not None:
            return self._to_view(existing, position), False

        if position.status != PositionStatus.COMMITTED or position.worker_id is None:
            raise AppError.conflict(
                f"Dispatch position is {position.status.value}, not COMMITTED — cannot create execution"
            )

        try:
            shift = self._shifts.create(
                dispatch_position_id=position.id,
                worker_id=position.worker_id,
                scheduled_for=work_requirement.requested_for,
            )
            self._db.commit()
        except IntegrityError:
            # Lost a race against another call creating an execution for
            # this same position — the unique constraint on
            # dispatch_position_id (see ShiftModel) is what actually
            # prevents the duplicate; this just turns that into the same
            # idempotent "return the existing one" response rather than a
            # 500. Not exercised by a concurrent-request test (see
            # docs/Execution.md "Concurrency"); the database constraint is
            # the real guarantee either way.
            self._db.rollback()
            existing = self._shifts.get_by_dispatch_position_id(dispatch_position_id)
            assert existing is not None
            return self._to_view(existing, position), False

        return self._to_view(shift, position), True

    # ------------------------------------------------------------------
    # GET /api/executions/{id}
    # POST /api/executions/{id}/check-in|start|complete
    # ------------------------------------------------------------------

    def get_execution(self, execution_id: str, *, requesting_user_id: str) -> ShiftView:
        shift, position = self._load_owned(execution_id, requesting_user_id)
        return self._to_view(shift, position)

    def check_in(self, execution_id: str, *, requesting_user_id: str) -> ShiftView:
        shift, position = self._load_owned(execution_id, requesting_user_id)
        execution_state_machine.assert_shift_transition(shift.status, ShiftStatus.CHECKED_IN)
        applied = self._shifts.try_transition(
            shift.id,
            expected_status=shift.status,
            new_status=ShiftStatus.CHECKED_IN,
            check_in_at=_utc_now(),
        )
        if not applied:
            raise AppError.conflict("Execution is no longer SCHEDULED")
        return self._commit_and_reload(shift.id, position)

    def start(self, execution_id: str, *, requesting_user_id: str) -> ShiftView:
        shift, position = self._load_owned(execution_id, requesting_user_id)
        execution_state_machine.assert_shift_transition(shift.status, ShiftStatus.WORKING)
        applied = self._shifts.try_transition(
            shift.id, expected_status=shift.status, new_status=ShiftStatus.WORKING
        )
        if not applied:
            raise AppError.conflict("Execution is no longer CHECKED_IN")
        return self._commit_and_reload(shift.id, position)

    def complete(self, execution_id: str, *, requesting_user_id: str) -> ShiftView:
        shift, position = self._load_owned(execution_id, requesting_user_id)
        execution_state_machine.assert_shift_transition(shift.status, ShiftStatus.COMPLETED)
        applied = self._shifts.try_transition(
            shift.id,
            expected_status=shift.status,
            new_status=ShiftStatus.COMPLETED,
            completed_at=_utc_now(),
        )
        if not applied:
            raise AppError.conflict("Execution is no longer WORKING")
        return self._commit_and_reload(shift.id, position)

    # ------------------------------------------------------------------

    def _load_owned(self, execution_id: str, requesting_user_id: str) -> tuple[Shift, DispatchPosition]:
        """Worker-ownership check lives here, not in the route — mirrors
        DispatchService's own offer-ownership checks — so it cannot be
        bypassed by calling the service directly. A worker may only ever
        resolve their OWN execution (see docs/Execution.md "Authorization")."""
        shift = self._shifts.get_by_id(execution_id)
        if shift is None:
            raise AppError.not_found("Execution not found")
        worker = self._workers.get_by_user_id(requesting_user_id)
        if worker is None or worker.id != shift.worker_id:
            raise AppError.forbidden("You may only operate on your own execution")
        position = self._positions.get_by_id(shift.dispatch_position_id)
        assert position is not None
        return shift, position

    def _commit_and_reload(self, shift_id: str, position: DispatchPosition) -> ShiftView:
        self._db.commit()
        refreshed = self._shifts.get_by_id(shift_id)
        assert refreshed is not None
        return self._to_view(refreshed, position)

    def _to_view(self, shift: Shift, position: DispatchPosition) -> ShiftView:
        return ShiftView(
            id=shift.id,
            dispatch_position_id=shift.dispatch_position_id,
            worker_id=shift.worker_id,
            work_requirement_id=position.work_requirement_id,
            crew_requirement_id=position.crew_requirement_id,
            scheduled_for=shift.scheduled_for,
            status=shift.status,
            check_in_at=shift.check_in_at,
            completed_at=shift.completed_at,
            created_at=shift.created_at,
            updated_at=shift.updated_at,
        )
