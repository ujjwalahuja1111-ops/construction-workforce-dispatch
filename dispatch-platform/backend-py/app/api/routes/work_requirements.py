"""
POST /api/work-requirements, GET /api/work-requirements/{id} — the
observable, testable end of Phases B/C/D/E/F/G: a contractor describes what
work is needed (trade/task + minimum level + quantity per line, plus
city/state/requested-for/notes), the system classifies and persists the
requirement, and returns the live-computed eligible/candidate workers and
fulfilment status for each line and for the requirement overall.

The contractor never browses worker profiles to get this result — see
`EligibleWorkerOut` below for exactly what is (and isn't) exposed about a
candidate.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.config import Settings, get_settings
from app.domain.enums import Role
from app.domain.views import (
    CrewRequirementResultView,
    DispatchOfferView,
    DispatchSummaryView,
    EligibleWorkerView,
    PositionDispatchOutcomeView,
    WorkRequirementResultView,
)
from app.infrastructure.security.jwt import TokenPayload
from app.services.classification_service import RequestedLine
from app.services.dispatch_service import DispatchService
from app.services.work_requirement_service import WorkRequirementService

router = APIRouter(prefix="/work-requirements", tags=["work-requirements"])

_require_contractor = require_role(Role.CONTRACTOR)
_require_contractor_or_admin = require_role(Role.CONTRACTOR, Role.ADMIN)


class RequirementLineIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: UUID = Field(alias="taskId")
    min_level: int = Field(alias="minLevel")
    quantity: int
    # Omitted/null => derive from the Task's own safety_qualification_required
    # flag (see classification_service.classify_lines).
    safety_qualification_required: bool | None = Field(default=None, alias="safetyQualificationRequired")

    @field_validator("min_level")
    @classmethod
    def _min_level_in_range(cls, v: int) -> int:
        if v not in (1, 2, 3, 4):
            raise ValueError("minLevel must be one of 1, 2, 3, 4")
        return v

    @field_validator("quantity")
    @classmethod
    def _quantity_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("quantity must be at least 1")
        return v


class WorkRequirementIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    city: str | None = None
    state: str | None = None
    requested_for: datetime | None = Field(default=None, alias="requestedFor")
    notes: str | None = None
    lines: list[RequirementLineIn] = Field(min_length=1)


class EligibleWorkerOut(BaseModel):
    """Deliberately thin: a worker id, their matched level/provenance, and
    city/state — enough for a contractor to trust the crew assembly, not
    enough to turn this into a worker-profile browse (no name, no phone).
    See docs/WorkRequirement.md."""

    model_config = ConfigDict(populate_by_name=True)

    worker_id: str = Field(serialization_alias="workerId")
    level: int
    provenance: str
    city: str | None
    state: str | None


class CrewRequirementOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    task_id: str = Field(serialization_alias="taskId")
    task_code: str = Field(serialization_alias="taskCode")
    task_name: str = Field(serialization_alias="taskName")
    trade_code: str = Field(serialization_alias="tradeCode")
    min_level: int = Field(serialization_alias="minLevel")
    quantity: int
    safety_qualification_required: bool = Field(serialization_alias="safetyQualificationRequired")
    status: str
    eligible_count: int = Field(serialization_alias="eligibleCount")
    eligible_workers: list[EligibleWorkerOut] = Field(serialization_alias="eligibleWorkers")
    candidates: list[EligibleWorkerOut]
    # Dispatch/commitment operational info — additive, see
    # FulfillmentStatus's "Two fulfilment signals, not one".
    required_positions: int = Field(serialization_alias="requiredPositions")
    committed_positions: int = Field(serialization_alias="committedPositions")
    open_positions: int = Field(serialization_alias="openPositions")
    escalated_positions: int = Field(serialization_alias="escalatedPositions")
    pending_offers: int = Field(serialization_alias="pendingOffers")
    dispatch_status: str = Field(serialization_alias="dispatchStatus")


class WorkRequirementOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    contractor_user_id: str = Field(serialization_alias="contractorUserId")
    city: str | None
    state: str | None
    requested_for: str | None = Field(serialization_alias="requestedFor")
    notes: str | None
    status: str
    created_at: str = Field(serialization_alias="createdAt")
    updated_at: str = Field(serialization_alias="updatedAt")
    lines: list[CrewRequirementOut]
    required_positions: int = Field(serialization_alias="requiredPositions")
    committed_positions: int = Field(serialization_alias="committedPositions")
    open_positions: int = Field(serialization_alias="openPositions")
    escalated_positions: int = Field(serialization_alias="escalatedPositions")
    pending_offers: int = Field(serialization_alias="pendingOffers")
    dispatch_status: str = Field(serialization_alias="dispatchStatus")


def _shape_worker(view: EligibleWorkerView) -> EligibleWorkerOut:
    return EligibleWorkerOut(
        worker_id=view.worker_id,
        level=view.level,
        provenance=view.provenance.value,
        city=view.city,
        state=view.state,
    )


def _shape_line(line: CrewRequirementResultView) -> CrewRequirementOut:
    return CrewRequirementOut(
        id=line.id,
        task_id=line.task_id,
        task_code=line.task_code,
        task_name=line.task_name,
        trade_code=line.trade_code,
        min_level=line.min_level,
        quantity=line.quantity,
        safety_qualification_required=line.safety_qualification_required,
        status=line.status.value,
        eligible_count=len(line.eligible_workers),
        eligible_workers=[_shape_worker(w) for w in line.eligible_workers],
        candidates=[_shape_worker(w) for w in line.candidates],
        required_positions=line.required_positions,
        committed_positions=line.committed_positions,
        open_positions=line.open_positions,
        escalated_positions=line.escalated_positions,
        pending_offers=line.pending_offers,
        dispatch_status=line.dispatch_status.value,
    )


def _shape(view: WorkRequirementResultView) -> WorkRequirementOut:
    return WorkRequirementOut(
        id=view.id,
        contractor_user_id=view.contractor_user_id,
        city=view.city,
        state=view.state,
        requested_for=view.requested_for.isoformat() if view.requested_for else None,
        notes=view.notes,
        status=view.status.value,
        created_at=view.created_at.isoformat(),
        updated_at=view.updated_at.isoformat(),
        lines=[_shape_line(line_view) for line_view in view.lines],
        required_positions=view.required_positions,
        committed_positions=view.committed_positions,
        open_positions=view.open_positions,
        escalated_positions=view.escalated_positions,
        pending_offers=view.pending_offers,
        dispatch_status=view.dispatch_status.value,
    )


@router.post("", response_model=WorkRequirementOut, response_model_by_alias=True, status_code=201)
def create_work_requirement(
    payload: WorkRequirementIn,
    token: TokenPayload = Depends(_require_contractor),
    db: Session = Depends(get_db),
) -> WorkRequirementOut:
    service = WorkRequirementService(db)
    requested_lines = [
        RequestedLine(
            task_id=str(line.task_id),
            min_level=line.min_level,
            quantity=line.quantity,
            safety_qualification_required=line.safety_qualification_required,
        )
        for line in payload.lines
    ]
    view = service.create(
        contractor_user_id=token["sub"],
        city=payload.city,
        state=payload.state,
        requested_for=payload.requested_for,
        notes=payload.notes,
        requested_lines=requested_lines,
    )
    return _shape(view)


@router.get("/{work_requirement_id}", response_model=WorkRequirementOut, response_model_by_alias=True)
def get_work_requirement(
    work_requirement_id: UUID,
    token: TokenPayload = Depends(_require_contractor_or_admin),
    db: Session = Depends(get_db),
) -> WorkRequirementOut:
    service = WorkRequirementService(db)
    view = service.get(
        str(work_requirement_id), requesting_user_id=token["sub"], requesting_role=token["role"]
    )
    return _shape(view)


class DispatchOfferOut(BaseModel):
    """Deliberately thin, same posture as EligibleWorkerOut — a dispatch
    summary reports outcomes, never a worker-browsing marketplace."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    worker_id: str = Field(serialization_alias="workerId")
    status: str
    expires_at: str = Field(serialization_alias="expiresAt")


class PositionOutcomeOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    position_id: str = Field(serialization_alias="positionId")
    crew_requirement_id: str = Field(serialization_alias="crewRequirementId")
    task_code: str = Field(serialization_alias="taskCode")
    status: str
    offer: DispatchOfferOut | None


class DispatchSummaryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    work_requirement_id: str = Field(serialization_alias="workRequirementId")
    positions: list[PositionOutcomeOut]
    required_positions: int = Field(serialization_alias="requiredPositions")
    committed_positions: int = Field(serialization_alias="committedPositions")
    open_positions: int = Field(serialization_alias="openPositions")
    escalated_positions: int = Field(serialization_alias="escalatedPositions")
    pending_offers: int = Field(serialization_alias="pendingOffers")
    dispatch_status: str = Field(serialization_alias="dispatchStatus")


def _shape_offer(offer: DispatchOfferView) -> DispatchOfferOut:
    return DispatchOfferOut(
        id=offer.id,
        worker_id=offer.worker_id,
        status=offer.status.value,
        expires_at=offer.expires_at.isoformat(),
    )


def _shape_outcome(outcome: PositionDispatchOutcomeView) -> PositionOutcomeOut:
    return PositionOutcomeOut(
        position_id=outcome.position_id,
        crew_requirement_id=outcome.crew_requirement_id,
        task_code=outcome.task_code,
        status=outcome.status.value,
        offer=_shape_offer(outcome.offer) if outcome.offer else None,
    )


def _shape_summary(summary: DispatchSummaryView) -> DispatchSummaryOut:
    return DispatchSummaryOut(
        work_requirement_id=summary.work_requirement_id,
        positions=[_shape_outcome(o) for o in summary.positions],
        required_positions=summary.required_positions,
        committed_positions=summary.committed_positions,
        open_positions=summary.open_positions,
        escalated_positions=summary.escalated_positions,
        pending_offers=summary.pending_offers,
        dispatch_status=summary.dispatch_status.value,
    )


@router.post(
    "/{work_requirement_id}/dispatch", response_model=DispatchSummaryOut, response_model_by_alias=True
)
def dispatch_work_requirement(
    work_requirement_id: UUID,
    token: TokenPayload = Depends(_require_contractor_or_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DispatchSummaryOut:
    service = DispatchService(db, settings)
    summary = service.dispatch(
        str(work_requirement_id), requesting_user_id=token["sub"], requesting_role=token["role"]
    )
    return _shape_summary(summary)
