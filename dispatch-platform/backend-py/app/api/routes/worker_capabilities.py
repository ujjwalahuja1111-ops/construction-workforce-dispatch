"""
POST/GET /api/worker/capabilities — Python port of the approved Patch 2
contract (patch2-contract-v2.md) and its TS implementation
(worker-capability.controller.ts + worker.routes.ts). Same auth boundary
(WORKER role only), same request/response shape, same status codes.

`taskId`/`workerId` naming stays camelCase on the wire (Pydantic aliases)
to match the existing TS API exactly — a mobile client (or anything else)
switching between the two backends during the migration sees the same JSON
shape either way.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_token, get_db, require_role
from app.domain.enums import Role
from app.domain.views import WorkerCapabilityView
from app.infrastructure.security.jwt import TokenPayload
from app.services.capability_service import CapabilityService

router = APIRouter(prefix="/worker", tags=["worker-capabilities"])

_require_worker = require_role(Role.WORKER)


class SelfDeclareIn(BaseModel):
    """Deliberately narrower than the internal capability shape: no
    `provenance`, no `workerId` field at all — there is no input path by
    which a caller could supply either (Pydantic drops unrecognized fields
    by default, so an extra `workerId`/`provenance` in the body is silently
    ignored, matching Contract §2/§6 exactly)."""

    model_config = ConfigDict(populate_by_name=True)

    task_id: UUID = Field(alias="taskId")
    level: int

    @field_validator("level")
    @classmethod
    def _level_in_range(cls, v: int) -> int:
        if v not in {1, 2, 3, 4}:
            raise ValueError("level must be one of 1, 2, 3, 4")
        return v


class TaskOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str
    name: str
    trade_code: str = Field(serialization_alias="tradeCode")


class CapabilityOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    task_id: str = Field(serialization_alias="taskId")
    level: int
    provenance: str
    created_at: str = Field(serialization_alias="createdAt")
    updated_at: str = Field(serialization_alias="updatedAt")
    task: TaskOut


class SelfDeclareOut(BaseModel):
    capability: CapabilityOut


class ListOut(BaseModel):
    capabilities: list[CapabilityOut]


def _shape(view: WorkerCapabilityView) -> CapabilityOut:
    return CapabilityOut(
        id=view.id,
        task_id=view.task_id,
        level=view.level,
        provenance=view.provenance.value,
        created_at=view.created_at.isoformat(),
        updated_at=view.updated_at.isoformat(),
        task=TaskOut(code=view.task_code, name=view.task_name, trade_code=view.trade_code),
    )


@router.post("/capabilities", response_model=SelfDeclareOut, response_model_by_alias=True)
def self_declare(
    payload: SelfDeclareIn,
    response: Response,
    token: TokenPayload = Depends(_require_worker),
    db: Session = Depends(get_db),
) -> SelfDeclareOut:
    service = CapabilityService(db)
    view, created = service.self_declare(token["sub"], str(payload.task_id), payload.level)
    response.status_code = 201 if created else 200
    return SelfDeclareOut(capability=_shape(view))


@router.get("/capabilities", response_model=ListOut, response_model_by_alias=True)
def list_capabilities(
    token: TokenPayload = Depends(_require_worker),
    db: Session = Depends(get_db),
) -> ListOut:
    service = CapabilityService(db)
    views = service.list_for_authenticated_worker(token["sub"])
    return ListOut(capabilities=[_shape(v) for v in views])


# `get_current_token` isn't used directly in this module, but importing it
# here keeps `_require_worker`'s dependency chain (require_role wraps
# get_current_token) discoverable from one place for anyone reading this
# route file top-to-bottom.
_ = get_current_token
