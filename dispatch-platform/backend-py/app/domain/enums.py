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
    """The outcome of matching a CrewRequirement line (or a whole
    WorkRequirement) against currently eligible workers — computed fresh on
    every read, never persisted, since worker availability/capability can
    change between requests. See docs/WorkRequirement.md "Fulfillment
    states" for the V1 policy and what's deliberately NOT built yet
    (adjacent-capability substitution, crew substitution) — those are
    reserved tiers between FULFILLED and ESCALATED that a future patch can
    add without changing this enum's meaning for existing callers.

    - FULFILLED: at least `quantity` eligible candidates were found.
    - PARTIALLY_FULFILLED: some, but fewer than `quantity`, eligible
      candidates were found — not a silent failure, a distinct state the
      caller must handle.
    - ESCALATED: zero eligible candidates — the requirement cannot be
      fulfilled from the current worker pool and needs human attention.
    """

    FULFILLED = "FULFILLED"
    PARTIALLY_FULFILLED = "PARTIALLY_FULFILLED"
    ESCALATED = "ESCALATED"
