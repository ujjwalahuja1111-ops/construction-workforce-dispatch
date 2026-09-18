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
