"""
Read-side view models: shapes assembled for a specific query/response, as
opposed to app.domain.entities (write-side aggregates). WorkerCapabilityView
carries the joined Task/Trade fields the API response needs (code, name,
tradeCode) without polluting the WorkerCapability entity itself with data
that belongs to a different aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.enums import CapabilityProvenance, FulfillmentStatus


@dataclass(slots=True)
class WorkerCapabilityView:
    id: str
    worker_id: str
    task_id: str
    level: int
    provenance: CapabilityProvenance
    created_at: datetime
    updated_at: datetime
    task_code: str
    task_name: str
    trade_code: str


@dataclass(slots=True)
class EligibleWorkerView:
    """One candidate for a CrewRequirement line — deliberately thin (no
    phone/name): this is a dispatch-candidate summary for the contractor,
    not a worker-profile browse. See docs/WorkRequirement.md "What the
    candidate view exposes, and what it doesn't"."""

    worker_id: str
    level: int
    provenance: CapabilityProvenance
    city: str | None
    state: str | None


@dataclass(slots=True)
class CrewRequirementResultView:
    """A CrewRequirement line plus its live-computed matching outcome.
    `eligible_workers` is every worker meeting task/level/safety/
    availability criteria (Phase E); `candidates` is the top `quantity` of
    those, deterministically ranked (Phase E "eligibility and ranking must
    remain separate concepts") — see app/services/matching_service.py."""

    id: str
    task_id: str
    task_code: str
    task_name: str
    trade_code: str
    min_level: int
    quantity: int
    safety_qualification_required: bool
    status: FulfillmentStatus
    eligible_workers: list[EligibleWorkerView] = field(default_factory=list)
    candidates: list[EligibleWorkerView] = field(default_factory=list)


@dataclass(slots=True)
class WorkRequirementResultView:
    id: str
    contractor_user_id: str
    city: str | None
    state: str | None
    requested_for: datetime | None
    notes: str | None
    status: FulfillmentStatus
    created_at: datetime
    updated_at: datetime
    lines: list[CrewRequirementResultView] = field(default_factory=list)
