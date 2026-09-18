"""
Phase E — capability-based matching foundation.

Two separate concerns, deliberately kept as two functions rather than one,
per the CTO's "eligibility and ranking must remain separate concepts":

- `eligible_workers` — everyone who satisfies task + minimum level +
  availability (`WorkerCapabilityRepository.list_capable_workers`) and,
  when the line requires it, holds the matching safety qualification. No
  ranking, no cap — this is the full correct candidate pool.
- `assemble_candidates` — takes that eligible pool and deterministically
  selects the top `quantity`. The pool is already ordered by the
  repository (capability level descending, then created_at ascending —
  highest-capability, then earliest-registered, wins ties), so this
  function is just a slice today. A future ranking algorithm (distance,
  trust, workload — see the legacy TS `DispatchEngine` for the shape of
  what that eventually becomes) replaces only this function; nothing above
  or below it needs to change.

Location matching is a plain case-insensitive equality check against
`Worker.city` — the only location data the Python `Worker` model carries
right now (no lat/lng; those live only on the TS side and were not ported
— see docs/PythonMigration.md). That is "location/radius where existing
infrastructure supports it," read literally: existing Python infrastructure
supports city, not radius.
"""

from __future__ import annotations

from app.domain.entities import CrewRequirement, WorkRequirement
from app.domain.views import EligibleWorkerView
from app.repositories.interfaces import WorkerCapabilityRepository, WorkerSafetyQualificationRepository


def eligible_workers(
    capabilities: WorkerCapabilityRepository,
    safety_qualifications: WorkerSafetyQualificationRepository,
    work_requirement: WorkRequirement,
    line: CrewRequirement,
) -> list[EligibleWorkerView]:
    candidates = capabilities.list_capable_workers(line.task_id, line.min_level)

    if work_requirement.city:
        wanted_city = work_requirement.city.strip().lower()
        candidates = [c for c in candidates if c.city and c.city.strip().lower() == wanted_city]

    if line.safety_qualification_required:
        candidates = [
            c for c in candidates if safety_qualifications.has_qualification(c.worker_id, line.task_id)
        ]

    return candidates


def assemble_candidates(eligible: list[EligibleWorkerView], quantity: int) -> list[EligibleWorkerView]:
    """`eligible` arrives already deterministically ordered; this only ever
    takes a prefix. Kept as its own function — not inlined into
    `eligible_workers` — so ranking stays a separate, independently
    replaceable step. Only correct for a single line considered in
    isolation — see `assemble_crew` for the multi-line case a real
    WorkRequirement needs."""
    return eligible[:quantity]


def assemble_crew(
    lines: list[tuple[CrewRequirement, list[EligibleWorkerView]]],
) -> dict[str, list[EligibleWorkerView]]:
    """Cross-line candidate assembly for one WorkRequirement.

    Two CrewRequirement lines on the same task (e.g. "1 Mason L3+" and "2
    Helper L1+" both against BRICKWORK_NEW_WALL) share an eligible pool —
    the mason's level-3 capability also clears the helper line's level-1
    bar. Naively taking `assemble_candidates` per line would let the same
    worker win a candidate slot on both lines, which isn't a real crew (one
    person cannot fill two concurrent slots on the same job). This
    function assigns each worker to at most one line's candidate list.

    Lines are processed most-specialized-first (highest `min_level`, ties
    broken by original line order) so a role with a higher capability bar
    gets first pick of a shared pool — still fully deterministic, still no
    ranking beyond what `eligible_workers` already established. Per-line
    `eligible_workers` results (computed separately, before this function
    runs) are never filtered by this — eligibility and assembly stay the
    separate concepts Phase E requires; this only decides who is
    *proposed*, not who *could* do the work.
    """
    ordered = sorted(lines, key=lambda pair: (-pair[0].min_level, pair[0].created_at))
    assigned: set[str] = set()
    result: dict[str, list[EligibleWorkerView]] = {}
    for line, eligible in ordered:
        picked: list[EligibleWorkerView] = []
        for candidate in eligible:
            if len(picked) >= line.quantity:
                break
            if candidate.worker_id in assigned:
                continue
            picked.append(candidate)
            assigned.add(candidate.worker_id)
        result[line.id] = picked
    return result
