"""
Deterministic state-transition validator for Shift/Execution — the same
pattern as app/services/dispatch_state_machine.py (an explicit transitions
table plus can_transition/assert_transition/is_terminal), deliberately kept
to the smallest linear chain the "COMMITTED POSITION -> MINIMAL SHIFT /
EXECUTION" patch asks for:

    SCHEDULED -> CHECKED_IN -> WORKING -> COMPLETED

No CHECKED_IN -> COMPLETED shortcut is included: there is no existing
convention in this codebase that compels one, and the order is explicit
that extra transitions should not be added without justification. No
cancellation/abandonment/replacement/paused/disputed states either — those
are future layers, not this patch's concern.

An illegal transition raises the same `AppError.invalid_state` (409) shape
`dispatch_state_machine` raises, so a client sees one consistent error
vocabulary for "this transition is never legal" across both state models.
"""

from __future__ import annotations

from app.core.errors import AppError
from app.domain.enums import ShiftStatus

SHIFT_TRANSITIONS: dict[ShiftStatus, frozenset[ShiftStatus]] = {
    ShiftStatus.SCHEDULED: frozenset({ShiftStatus.CHECKED_IN}),
    ShiftStatus.CHECKED_IN: frozenset({ShiftStatus.WORKING}),
    ShiftStatus.WORKING: frozenset({ShiftStatus.COMPLETED}),
    ShiftStatus.COMPLETED: frozenset(),
}


def can_transition_shift(current: ShiftStatus, target: ShiftStatus) -> bool:
    return target in SHIFT_TRANSITIONS[current]


def assert_shift_transition(current: ShiftStatus, target: ShiftStatus) -> None:
    if not can_transition_shift(current, target):
        raise AppError.invalid_state(f"Cannot transition execution from {current.value} to {target.value}")


def is_shift_terminal(status: ShiftStatus) -> bool:
    return len(SHIFT_TRANSITIONS[status]) == 0
