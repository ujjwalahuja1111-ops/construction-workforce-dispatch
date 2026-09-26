"""
POST /api/dispatch-positions/{position_id}/execution — turns a COMMITTED
DispatchPosition into a Shift/Execution record. CONTRACTOR-owner or ADMIN,
the same ownership boundary `DispatchService.dispatch` already uses:
creating an execution is an operational trigger on the contractor's own
work requirement, not a worker action. Idempotent — a repeated call for a
position that already has an execution returns the existing one (200)
rather than creating a second (see ExecutionService.create_execution).

GET /api/executions/{id}, POST .../check-in, .../start, .../complete — a
worker resolving their own execution. WORKER only, own execution only,
enforced in ExecutionService (not here) so it cannot be bypassed by calling
the service directly. See docs/Execution.md.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.domain.enums import Role
from app.domain.views import ShiftView
from app.infrastructure.security.jwt import TokenPayload
from app.services.execution_service import ExecutionService

router = APIRouter(tags=["executions"])

_require_contractor_or_admin = require_role(Role.CONTRACTOR, Role.ADMIN)
_require_worker = require_role(Role.WORKER)


class ExecutionOut(BaseModel):
    """Deliberately thin, same posture as the dispatch views: enough for a
    future UI to render the assignment and its state, nothing about
    payroll/GPS/ratings — those are future layers (see docs/Execution.md)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    dispatch_position_id: str = Field(serialization_alias="dispatchPositionId")
    worker_id: str = Field(serialization_alias="workerId")
    work_requirement_id: str = Field(serialization_alias="workRequirementId")
    crew_requirement_id: str = Field(serialization_alias="crewRequirementId")
    scheduled_for: str | None = Field(serialization_alias="scheduledFor")
    status: str
    check_in_at: str | None = Field(serialization_alias="checkInAt")
    completed_at: str | None = Field(serialization_alias="completedAt")


def _shape(view: ShiftView) -> ExecutionOut:
    return ExecutionOut(
        id=view.id,
        dispatch_position_id=view.dispatch_position_id,
        worker_id=view.worker_id,
        work_requirement_id=view.work_requirement_id,
        crew_requirement_id=view.crew_requirement_id,
        scheduled_for=view.scheduled_for.isoformat() if view.scheduled_for else None,
        status=view.status.value,
        check_in_at=view.check_in_at.isoformat() if view.check_in_at else None,
        completed_at=view.completed_at.isoformat() if view.completed_at else None,
    )


@router.post(
    "/dispatch-positions/{position_id}/execution",
    response_model=ExecutionOut,
    response_model_by_alias=True,
)
def create_execution(
    position_id: UUID,
    response: Response,
    token: TokenPayload = Depends(_require_contractor_or_admin),
    db: Session = Depends(get_db),
) -> ExecutionOut:
    service = ExecutionService(db)
    view, created = service.create_execution(
        str(position_id), requesting_user_id=token["sub"], requesting_role=token["role"]
    )
    # 201 on genuine creation, 200 when idempotently returning an existing
    # execution — a repeated call is not an error, but it also isn't "a new
    # thing was just created" (see docs/Execution.md "Hard invariant").
    response.status_code = 201 if created else 200
    return _shape(view)


@router.get("/executions/{execution_id}", response_model=ExecutionOut, response_model_by_alias=True)
def get_execution(
    execution_id: UUID,
    token: TokenPayload = Depends(_require_worker),
    db: Session = Depends(get_db),
) -> ExecutionOut:
    service = ExecutionService(db)
    view = service.get_execution(str(execution_id), requesting_user_id=token["sub"])
    return _shape(view)


@router.post(
    "/executions/{execution_id}/check-in", response_model=ExecutionOut, response_model_by_alias=True
)
def check_in(
    execution_id: UUID,
    token: TokenPayload = Depends(_require_worker),
    db: Session = Depends(get_db),
) -> ExecutionOut:
    service = ExecutionService(db)
    view = service.check_in(str(execution_id), requesting_user_id=token["sub"])
    return _shape(view)


@router.post("/executions/{execution_id}/start", response_model=ExecutionOut, response_model_by_alias=True)
def start(
    execution_id: UUID,
    token: TokenPayload = Depends(_require_worker),
    db: Session = Depends(get_db),
) -> ExecutionOut:
    service = ExecutionService(db)
    view = service.start(str(execution_id), requesting_user_id=token["sub"])
    return _shape(view)


@router.post(
    "/executions/{execution_id}/complete", response_model=ExecutionOut, response_model_by_alias=True
)
def complete(
    execution_id: UUID,
    token: TokenPayload = Depends(_require_worker),
    db: Session = Depends(get_db),
) -> ExecutionOut:
    service = ExecutionService(db)
    view = service.complete(str(execution_id), requesting_user_id=token["sub"])
    return _shape(view)
