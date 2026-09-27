"""
GET /api/dispatch/offers — a worker discovering their own offers (any
status), POST /api/dispatch/offers/{offer_id}/accept, POST .../decline — a
worker resolving their own dispatch offer, and
POST /api/dispatch/offers/expire — the internal/service endpoint that
processes due expiries (no background scheduler exists on either backend
today; see docs/Dispatch.md "Expiry").

Authorization mirrors the CTO order's rules exactly: a worker may only
see/accept/decline THEIR OWN offers (enforced in DispatchService, not
here, so the check can't be bypassed by calling the service directly) —
never another worker's, and never a contractor shortcut around it. The
expiry endpoint is ADMIN-only (an internal operational trigger, not
something a contractor or worker calls directly).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.config import Settings, get_settings
from app.domain.enums import Role
from app.domain.views import (
    CommittedAssignmentView,
    ExpireOffersResultView,
    MyDispatchOfferView,
    OfferActionResultView,
)
from app.infrastructure.security.jwt import TokenPayload
from app.services.dispatch_service import DispatchService

router = APIRouter(prefix="/dispatch/offers", tags=["dispatch-offers"])

_require_worker = require_role(Role.WORKER)
_require_admin = require_role(Role.ADMIN)


class MyOfferOut(BaseModel):
    """Deliberately thin, same posture as EligibleWorkerOut/DispatchOfferOut
    — enough for a worker to understand and act on their own offer, never a
    worker-browsing surface. See MyDispatchOfferView's docstring."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    status: str
    created_at: str = Field(serialization_alias="createdAt")
    expires_at: str = Field(serialization_alias="expiresAt")
    responded_at: str | None = Field(serialization_alias="respondedAt")
    position_id: str = Field(serialization_alias="positionId")
    work_requirement_id: str = Field(serialization_alias="workRequirementId")
    crew_requirement_id: str = Field(serialization_alias="crewRequirementId")
    task_code: str = Field(serialization_alias="taskCode")
    task_name: str = Field(serialization_alias="taskName")
    min_level: int = Field(serialization_alias="minLevel")
    city: str | None
    state: str | None
    requested_for: str | None = Field(serialization_alias="requestedFor")


def _shape_my_offer(view: MyDispatchOfferView) -> MyOfferOut:
    return MyOfferOut(
        id=view.id,
        status=view.status.value,
        created_at=view.created_at.isoformat(),
        expires_at=view.expires_at.isoformat(),
        responded_at=view.responded_at.isoformat() if view.responded_at else None,
        position_id=view.position_id,
        work_requirement_id=view.work_requirement_id,
        crew_requirement_id=view.crew_requirement_id,
        task_code=view.task_code,
        task_name=view.task_name,
        min_level=view.min_level,
        city=view.city,
        state=view.state,
        requested_for=view.requested_for.isoformat() if view.requested_for else None,
    )


@router.get("", response_model=list[MyOfferOut], response_model_by_alias=True)
def list_my_offers(
    token: TokenPayload = Depends(_require_worker),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[MyOfferOut]:
    service = DispatchService(db, settings)
    views = service.list_my_offers(requesting_user_id=token["sub"])
    return [_shape_my_offer(v) for v in views]


class CommittedAssignmentOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    position_id: str = Field(serialization_alias="positionId")
    work_requirement_id: str = Field(serialization_alias="workRequirementId")
    crew_requirement_id: str = Field(serialization_alias="crewRequirementId")
    worker_id: str = Field(serialization_alias="workerId")
    offer_id: str = Field(serialization_alias="offerId")
    committed_at: str = Field(serialization_alias="committedAt")
    work_requirement_dispatch_status: str = Field(serialization_alias="workRequirementDispatchStatus")


class OfferActionResultOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    offer_id: str = Field(serialization_alias="offerId")
    position_id: str = Field(serialization_alias="positionId")
    offer_status: str = Field(serialization_alias="offerStatus")
    position_status: str = Field(serialization_alias="positionStatus")


class ExpireOffersResultOut(BaseModel):
    processed: list[OfferActionResultOut]


def _shape_assignment(view: CommittedAssignmentView) -> CommittedAssignmentOut:
    return CommittedAssignmentOut(
        position_id=view.position_id,
        work_requirement_id=view.work_requirement_id,
        crew_requirement_id=view.crew_requirement_id,
        worker_id=view.worker_id,
        offer_id=view.offer_id,
        committed_at=view.committed_at.isoformat(),
        work_requirement_dispatch_status=view.work_requirement_dispatch_status.value,
    )


def _shape_action(view: OfferActionResultView) -> OfferActionResultOut:
    return OfferActionResultOut(
        offer_id=view.offer_id,
        position_id=view.position_id,
        offer_status=view.offer_status.value,
        position_status=view.position_status.value,
    )


@router.post(
    "/{offer_id}/accept", response_model=CommittedAssignmentOut, response_model_by_alias=True
)
def accept_offer(
    offer_id: UUID,
    token: TokenPayload = Depends(_require_worker),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CommittedAssignmentOut:
    service = DispatchService(db, settings)
    result = service.accept_offer(str(offer_id), requesting_user_id=token["sub"])
    return _shape_assignment(result)


@router.post("/{offer_id}/decline", response_model=OfferActionResultOut, response_model_by_alias=True)
def decline_offer(
    offer_id: UUID,
    token: TokenPayload = Depends(_require_worker),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> OfferActionResultOut:
    service = DispatchService(db, settings)
    result = service.decline_offer(str(offer_id), requesting_user_id=token["sub"])
    return _shape_action(result)


@router.post("/expire", response_model=ExpireOffersResultOut, response_model_by_alias=True)
def expire_offers(
    token: TokenPayload = Depends(_require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ExpireOffersResultOut:
    service = DispatchService(db, settings)
    result: ExpireOffersResultView = service.expire_due_offers()
    return ExpireOffersResultOut(processed=[_shape_action(o) for o in result.processed])
