"""
Phase G — fulfilment resilience.

A deterministic, explainable V1 policy only: no adjacent-capability
substitution, no crew substitution — those are reserved tiers (see
`FulfillmentStatus` in app/domain/enums.py) that a future patch can add
without changing what this enum means to existing callers. What this patch
guarantees is that a caller always gets one of three explicit states, never
a silent empty result:

- FULFILLED — enough candidates were actually assigned to the line.
- PARTIALLY_FULFILLED — some, but not enough.
- ESCALATED — none at all; this cannot be filled from the current worker
  pool and needs human attention.

Safety-critical minimum competency is not a "tier" here — it's already a
hard filter inside `matching_service.eligible_workers`, so a worker missing
a required qualification simply never appears in the eligible pool this
module scores against.

`line_status` takes the ASSEMBLED candidate count, not the raw eligible
count. They can differ: two lines on the same task can share an eligible
pool (a level-3 mason also clears a level-1+ helper line), and
`matching_service.assemble_crew` assigns each worker to at most one line —
so a line can show eligible workers on paper while having zero candidates
actually left for it once a higher-priority line has claimed them. Status
must reflect "can we actually crew this," which is the assembled outcome,
not raw eligibility (see docs/WorkRequirement.md "Why status is based on
assembled candidates, not raw eligibility").
"""

from __future__ import annotations

from app.domain.enums import FulfillmentStatus


def line_status(assigned_count: int, quantity: int) -> FulfillmentStatus:
    if assigned_count >= quantity:
        return FulfillmentStatus.FULFILLED
    if assigned_count > 0:
        return FulfillmentStatus.PARTIALLY_FULFILLED
    return FulfillmentStatus.ESCALATED


def dispatch_line_status(*, committed_count: int, escalated_count: int, quantity: int) -> FulfillmentStatus:
    """The commitment-based counterpart to `line_status` above — see
    `FulfillmentStatus`'s docstring "Two fulfilment signals, not one" and
    docs/Dispatch.md. Driven by actual DispatchPosition state, not the
    assembled-candidate count:

    - FULFILLED: every position for this line is COMMITTED.
    - ESCALATED: at least one position has exhausted every valid candidate
      (position-level ESCALATED) — "no viable path for a required
      position," regardless of how many other positions on the same line
      are already committed.
    - PARTIALLY_FULFILLED: anything else — some committed, some still
      open/offered and not (yet) escalated. This deliberately covers "not
      yet dispatched at all" as well as "in progress": neither is a
      failure state, so neither is ESCALATED; "unresolved" is the accurate
      word for both.
    """
    if committed_count >= quantity:
        return FulfillmentStatus.FULFILLED
    if escalated_count > 0:
        return FulfillmentStatus.ESCALATED
    return FulfillmentStatus.PARTIALLY_FULFILLED


def overall_status(line_statuses: list[FulfillmentStatus]) -> FulfillmentStatus:
    """A WorkRequirement with zero lines is treated as ESCALATED, not
    FULFILLED — classify_lines() already rejects an empty line list before
    persistence, so this only matters as a defensive default, never a real
    code path today."""
    if not line_statuses:
        return FulfillmentStatus.ESCALATED
    if any(s == FulfillmentStatus.ESCALATED for s in line_statuses):
        return FulfillmentStatus.ESCALATED
    if any(s == FulfillmentStatus.PARTIALLY_FULFILLED for s in line_statuses):
        return FulfillmentStatus.PARTIALLY_FULFILLED
    return FulfillmentStatus.FULFILLED
