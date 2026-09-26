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

from app.domain.enums import CapabilityProvenance, FulfillmentStatus, OfferStatus, PositionStatus


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
    # Dispatch/commitment operational info (see FulfillmentStatus docstring
    # "Two fulfilment signals, not one") — additive, never replaces the
    # candidate-based fields above.
    required_positions: int = 0
    committed_positions: int = 0
    open_positions: int = 0
    escalated_positions: int = 0
    pending_offers: int = 0
    dispatch_status: FulfillmentStatus = FulfillmentStatus.ESCALATED


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
    # Aggregated across `lines` — see CrewRequirementResultView.
    required_positions: int = 0
    committed_positions: int = 0
    open_positions: int = 0
    escalated_positions: int = 0
    pending_offers: int = 0
    dispatch_status: FulfillmentStatus = FulfillmentStatus.ESCALATED


@dataclass(slots=True)
class DispatchOfferView:
    """A DispatchOffer plus enough context (task/position identity) for an
    API response, without exposing a worker-browsing surface — see
    docs/Dispatch.md."""

    id: str
    position_id: str
    work_requirement_id: str
    crew_requirement_id: str
    worker_id: str
    status: OfferStatus
    created_at: datetime
    expires_at: datetime
    responded_at: datetime | None


@dataclass(slots=True)
class PositionDispatchOutcomeView:
    """One position's outcome from a single `POST .../dispatch` call —
    the dispatch summary's per-position line item."""

    position_id: str
    crew_requirement_id: str
    task_code: str
    status: PositionStatus
    offer: DispatchOfferView | None


@dataclass(slots=True)
class DispatchSummaryView:
    """The response of `POST /api/work-requirements/{id}/dispatch` —
    "here's what happened," never a worker-browsing marketplace: no
    candidate pool is exposed here, only the outcome per position."""

    work_requirement_id: str
    positions: list[PositionDispatchOutcomeView]
    required_positions: int
    committed_positions: int
    open_positions: int
    escalated_positions: int
    pending_offers: int
    dispatch_status: FulfillmentStatus


@dataclass(slots=True)
class CommittedAssignmentView:
    """The response of a successful `POST /dispatch/offers/{id}/accept` —
    "here is the committed assignment," per the CTO order's step 11."""

    position_id: str
    work_requirement_id: str
    crew_requirement_id: str
    worker_id: str
    offer_id: str
    committed_at: datetime
    work_requirement_dispatch_status: FulfillmentStatus


@dataclass(slots=True)
class OfferActionResultView:
    """The response of `POST /dispatch/offers/{id}/decline` (and reused for
    the internal expiry endpoint's per-offer outcome)."""

    offer_id: str
    position_id: str
    offer_status: OfferStatus
    position_status: PositionStatus


@dataclass(slots=True)
class ExpireOffersResultView:
    processed: list[OfferActionResultView]
