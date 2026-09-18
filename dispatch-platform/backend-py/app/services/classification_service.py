"""
Phase D — work classification. Deterministic and structured, no AI: turns
a raw list of client-requested lines (task id + minimum level + quantity)
into validated `NewCrewRequirementLine` domain values.

This is intentionally a single small, swappable function — not a class,
not a pipeline of strategies — precisely so a future AI-based classifier
(turning free text like "build a 1,000 sq ft brick wall" into the same
`RequestedLine` shape this module already validates) can replace only
`classify_lines` without touching `CrewRequirement`, `MatchingService`, or
the API layer. See docs/WorkRequirement.md "Classification: V1 and what
comes after".
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import AppError
from app.domain.entities import NewCrewRequirementLine
from app.repositories.interfaces import TaskRepository


@dataclass(slots=True)
class RequestedLine:
    """Raw input from the API layer, before classification/validation."""

    task_id: str
    min_level: int
    quantity: int
    # None => derive from the Task's own safety_qualification_required flag
    # (see docstring on CrewRequirement for why this is a snapshot).
    safety_qualification_required: bool | None


def classify_lines(
    tasks: TaskRepository, requested: list[RequestedLine]
) -> list[NewCrewRequirementLine]:
    """Raises AppError.bad_request/not_found on the first invalid line —
    nothing is written by this function (it's pure), so the caller can
    validate the whole batch before any persistence happens."""
    if not requested:
        raise AppError.bad_request("A work requirement needs at least one requirement line")

    classified: list[NewCrewRequirementLine] = []
    for line in requested:
        if line.min_level not in (1, 2, 3, 4):
            raise AppError.bad_request("minLevel must be one of 1, 2, 3, 4")
        if line.quantity < 1:
            raise AppError.bad_request("quantity must be at least 1")

        task = tasks.get_by_id(line.task_id)
        if task is None or not task.is_active:
            raise AppError.not_found(f"Task {line.task_id} not found")

        safety_required = (
            line.safety_qualification_required
            if line.safety_qualification_required is not None
            else task.safety_qualification_required
        )
        classified.append(
            NewCrewRequirementLine(
                task_id=task.id,
                min_level=line.min_level,
                quantity=line.quantity,
                safety_qualification_required=safety_required,
            )
        )
    return classified
