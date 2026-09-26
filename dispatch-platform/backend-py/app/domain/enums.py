"""
Domain enums. Values are byte-for-byte identical to the approved TypeScript
domain model (backend/src/types/domain.ts) — these are stored as plain
strings/ints in both backends' databases, and preserving the exact values is
what keeps the *semantics* of the already-approved capability model
(Trade/Task/WorkerCapability/Assessment) intact across the migration, even
though the two databases are not the same database.
"""

from enum import IntEnum, StrEnum


class Role(StrEnum):
    WORKER = "WORKER"
    CONTRACTOR = "CONTRACTOR"
    ADMIN = "ADMIN"


class CapabilityLevel(IntEnum):
    L1 = 1  # Assist / Directed
    L2 = 2  # Independent, standard work
    L3 = 3  # Independent + basic troubleshooting
    L4 = 4  # Expert / complex & novel


class CapabilityProvenance(StrEnum):
    SELF_DECLARED = "SELF_DECLARED"
    ASSESSED = "ASSESSED"
    PRACTICALLY_VERIFIED = "PRACTICALLY_VERIFIED"
    PERFORMANCE_CONFIRMED = "PERFORMANCE_CONFIRMED"


class AssessmentType(StrEnum):
    SELF_DECLARATION = "SELF_DECLARATION"
    KNOWLEDGE_TEST = "KNOWLEDGE_TEST"
    PRACTICAL_VERIFICATION = "PRACTICAL_VERIFICATION"
    PERFORMANCE_REVIEW = "PERFORMANCE_REVIEW"


class FulfillmentStatus(StrEnum):
    """Shared by two distinct computations — see docs/Dispatch.md "Two
    fulfilment signals, not one" for the full rationale:

    - `WorkRequirementResultView.status` / `CrewRequirementResultView.status`
      (Phase F/G, unchanged by the dispatch patch): candidate-assembly
      based — "could this plausibly be crewed given who's currently
      eligible." At least `quantity` assembled candidates -> FULFILLED;
      some but not enough -> PARTIALLY_FULFILLED; none -> ESCALATED.
    - `.dispatch_status` (new): actual-commitment based — "has this been
      crewed via real offers and acceptances." All required positions
      COMMITTED -> FULFILLED; some committed, none escalated ->
      PARTIALLY_FULFILLED (covers "not yet dispatched" and "in progress"
      alike — both are still workable, not a failure); any position that
      has exhausted every valid candidate -> ESCALATED. See
      app/services/fulfillment.py `dispatch_line_status`.

    CANDIDATES ≠ COMMITTED WORKERS: the two can and do disagree (a line can
    show FULFILLED candidate coverage while nothing has actually been
    dispatched yet, hence PARTIALLY_FULFILLED/"unresolved" dispatch_status)
    — that disagreement is the point, not a bug. Adjacent-capability
    substitution and crew substitution remain deliberately unbuilt tiers
    reserved on this same enum for both computations.
    """

    FULFILLED = "FULFILLED"
    PARTIALLY_FULFILLED = "PARTIALLY_FULFILLED"
    ESCALATED = "ESCALATED"


class PositionStatus(StrEnum):
    """Dispatch Position lifecycle. Each unit of a CrewRequirement's
    `quantity` is one independently fulfillable position — this is the
    minimum state model the CTO's "DISPATCH + COMMITMENT" order asks for:

        OPEN -> OFFERED -> COMMITTED

    plus the explicit failure/recovery transitions OFFERED->OPEN (decline
    or expiry reopens the position), OFFERED->CANCELLED, and
    COMMITTED->OPEN — the last one reachable ONLY through an explicit
    replacement/re-dispatch operation, never an arbitrary status mutation
    (see app/services/dispatch_state_machine.py and
    DispatchService.accept_offer's docstring for how that's enforced in
    code, not just by convention).

    ESCALATED is reached only from OPEN/ESCALATED, and only when a dispatch
    attempt finds zero valid candidates for that position — an explicit
    "cannot currently be filled" signal, never a position silently left
    OPEN forever with no visible reason. An ESCALATED position is still
    reconsidered on the next dispatch call (new workers may register
    capability later), so it is not a dead end.
    """

    OPEN = "OPEN"
    OFFERED = "OFFERED"
    COMMITTED = "COMMITTED"
    ESCALATED = "ESCALATED"
    CANCELLED = "CANCELLED"


class OfferStatus(StrEnum):
    """Dispatch Offer lifecycle — one position, one worker. Kept
    intentionally small per the CTO's order ("keep the state model
    small"): every terminal state is reached directly from PENDING, no
    intermediate states."""

    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
