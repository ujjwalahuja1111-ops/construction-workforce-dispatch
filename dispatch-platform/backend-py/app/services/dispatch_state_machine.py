"""
Deterministic state-transition validators for DispatchPosition and
DispatchOffer, mirroring the legacy TypeScript `ShiftEngine`'s pattern
(backend/src/engines/shift.engine.ts) — an explicit transitions table plus
`can_transition`/`assert_transition`/`is_terminal`, so an illegal mutation
(e.g. OPEN -> COMMITTED directly, skipping an offer entirely; or an
arbitrary COMMITTED -> OPEN outside the one sanctioned redispatch path)
raises the same `AppError.invalid_state` shape the TS engine raises via
`AppError.invalidState`, rather than silently corrupting state.

COMMITTED -> OPEN is deliberately present in the position table (a
redispatch/replacement must be able to reopen a committed position) but the
ONLY caller that ever requests it is `DispatchService`'s internal
replacement path — no route exposes a generic "set position status"
endpoint, so an ordinary API consumer can never trigger this transition
arbitrarily. This module enforces which transitions are *possible*; the
service layer enforces which ones are *reachable*.

These tables are the source of truth for "is this transition legal at all."
The atomic, race-safe *application* of a transition (the concurrency guard
behind TEST 8, the double-accept race) lives in the repository layer's
`try_transition_*` methods — see docs/Dispatch.md "Two-layer transition
safety" for why both layers exist and neither is a substitute for the
other.
"""

from __future__ import annotations

from app.core.errors import AppError
from app.domain.enums import OfferStatus, PositionStatus

POSITION_TRANSITIONS: dict[PositionStatus, frozenset[PositionStatus]] = {
    PositionStatus.OPEN: frozenset(
        {PositionStatus.OFFERED, PositionStatus.CANCELLED, PositionStatus.ESCALATED}
    ),
    PositionStatus.OFFERED: frozenset(
        {PositionStatus.COMMITTED, PositionStatus.OPEN, PositionStatus.CANCELLED}
    ),
    PositionStatus.COMMITTED: frozenset({PositionStatus.OPEN}),
    PositionStatus.ESCALATED: frozenset({PositionStatus.OFFERED, PositionStatus.CANCELLED}),
    PositionStatus.CANCELLED: frozenset(),
}

OFFER_TRANSITIONS: dict[OfferStatus, frozenset[OfferStatus]] = {
    OfferStatus.PENDING: frozenset(
        {OfferStatus.ACCEPTED, OfferStatus.DECLINED, OfferStatus.EXPIRED, OfferStatus.CANCELLED}
    ),
    OfferStatus.ACCEPTED: frozenset(),
    OfferStatus.DECLINED: frozenset(),
    OfferStatus.EXPIRED: frozenset(),
    OfferStatus.CANCELLED: frozenset(),
}


def can_transition_position(current: PositionStatus, target: PositionStatus) -> bool:
    return target in POSITION_TRANSITIONS[current]


def assert_position_transition(current: PositionStatus, target: PositionStatus) -> None:
    if not can_transition_position(current, target):
        raise AppError.invalid_state(
            f"Cannot transition dispatch position from {current.value} to {target.value}"
        )


def is_position_terminal(status: PositionStatus) -> bool:
    return len(POSITION_TRANSITIONS[status]) == 0


def can_transition_offer(current: OfferStatus, target: OfferStatus) -> bool:
    return target in OFFER_TRANSITIONS[current]


def assert_offer_transition(current: OfferStatus, target: OfferStatus) -> None:
    if not can_transition_offer(current, target):
        raise AppError.invalid_state(
            f"Cannot transition dispatch offer from {current.value} to {target.value}"
        )


def is_offer_terminal(status: OfferStatus) -> bool:
    return len(OFFER_TRANSITIONS[status]) == 0
