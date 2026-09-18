"""
Phases B/C/F orchestration — turns a raw work request into a persisted
WorkRequirement + CrewRequirement lines (via classification_service), then
computes each line's live matching/fulfilment outcome (via
matching_service + fulfillment). This is the

    CLIENT WORK REQUEST -> CLASSIFIED REQUIREMENT -> CREW REQUIREMENT
        -> ELIGIBLE WORKERS -> CREW ASSEMBLY / DISPATCH CANDIDATES

pipeline the CTO's Phase F asks for, delivered as one observable, testable
read: `get()` recomputes the match live on every call rather than trusting
a stored snapshot, because worker availability/capability can change
between requests and a stale "eligible" list would be exactly the kind of
silent failure Phase G exists to prevent.

What this does NOT do: create a Job/JobOffer/Shift, or notify/assign any
worker. Turning a crew-assembly result into an actual dispatch is the
legacy TS `DispatchEngine`'s job today (see docs/DispatchEngine.md); this
patch stops at "here are the correct candidates," which is what Phase F
explicitly asks for and no further. See docs/WorkRequirement.md "What
Phase F does NOT do".
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.entities import WorkRequirement
from app.domain.enums import Role
from app.domain.views import CrewRequirementResultView, WorkRequirementResultView
from app.repositories.sqlalchemy_repositories import (
    SqlAlchemyCrewRequirementRepository,
    SqlAlchemyTaskRepository,
    SqlAlchemyTradeRepository,
    SqlAlchemyWorkerCapabilityRepository,
    SqlAlchemyWorkerSafetyQualificationRepository,
    SqlAlchemyWorkRequirementRepository,
)
from app.services import classification_service, fulfillment, matching_service
from app.services.classification_service import RequestedLine


class WorkRequirementService:
    def __init__(self, db: Session) -> None:
        self._trades = SqlAlchemyTradeRepository(db)
        self._tasks = SqlAlchemyTaskRepository(db)
        self._work_requirements = SqlAlchemyWorkRequirementRepository(db)
        self._crew_requirements = SqlAlchemyCrewRequirementRepository(db)
        self._capabilities = SqlAlchemyWorkerCapabilityRepository(db)
        self._safety_qualifications = SqlAlchemyWorkerSafetyQualificationRepository(db)

    def create(
        self,
        *,
        contractor_user_id: str,
        city: str | None,
        state: str | None,
        requested_for: datetime | None,
        notes: str | None,
        requested_lines: list[RequestedLine],
    ) -> WorkRequirementResultView:
        # Classification runs BEFORE any write: an invalid line rejects the
        # whole request with nothing persisted, rather than leaving a
        # WorkRequirement with a partial/invalid set of lines.
        classified = classification_service.classify_lines(self._tasks, requested_lines)

        work_requirement = self._work_requirements.create(
            contractor_user_id=contractor_user_id,
            city=city,
            state=state,
            requested_for=requested_for,
            notes=notes,
        )
        self._crew_requirements.create_many(work_requirement.id, classified)

        return self._to_result_view(work_requirement)

    def get(
        self, work_requirement_id: str, *, requesting_user_id: str, requesting_role: str
    ) -> WorkRequirementResultView:
        work_requirement = self._work_requirements.get_by_id(work_requirement_id)
        if work_requirement is None:
            raise AppError.not_found("Work requirement not found")
        if requesting_role != Role.ADMIN and work_requirement.contractor_user_id != requesting_user_id:
            raise AppError.forbidden("You may only view your own work requirements")
        return self._to_result_view(work_requirement)

    def _to_result_view(self, work_requirement: WorkRequirement) -> WorkRequirementResultView:
        lines = self._crew_requirements.list_for_work_requirement(work_requirement.id)

        # Pass 1: per-line eligibility, independent of every other line —
        # Phase E's "eligible_workers" is always the full, undeduplicated
        # pool (see matching_service.eligible_workers).
        eligible_by_line = {
            line.id: matching_service.eligible_workers(
                self._capabilities, self._safety_qualifications, work_requirement, line
            )
            for line in lines
        }

        # Pass 2: assemble the crew ACROSS all lines at once, so the same
        # worker is never proposed as a candidate for two lines in this
        # requirement (see matching_service.assemble_crew for why a
        # per-line assemble_candidates call isn't sufficient here).
        candidates_by_line = matching_service.assemble_crew(
            [(line, eligible_by_line[line.id]) for line in lines]
        )

        line_views: list[CrewRequirementResultView] = []
        for line in lines:
            task = self._tasks.get_by_id(line.task_id)
            assert task is not None  # Restrict-on-delete guarantees this
            trade = self._trades.get_by_id(task.trade_id)
            assert trade is not None

            candidates = candidates_by_line[line.id]
            status = fulfillment.line_status(len(candidates), line.quantity)

            line_views.append(
                CrewRequirementResultView(
                    id=line.id,
                    task_id=line.task_id,
                    task_code=task.code,
                    task_name=task.name,
                    trade_code=trade.code,
                    min_level=line.min_level,
                    quantity=line.quantity,
                    safety_qualification_required=line.safety_qualification_required,
                    status=status,
                    eligible_workers=eligible_by_line[line.id],
                    candidates=candidates,
                )
            )

        overall = fulfillment.overall_status([lv.status for lv in line_views])
        return WorkRequirementResultView(
            id=work_requirement.id,
            contractor_user_id=work_requirement.contractor_user_id,
            city=work_requirement.city,
            state=work_requirement.state,
            requested_for=work_requirement.requested_for,
            notes=work_requirement.notes,
            status=overall,
            created_at=work_requirement.created_at,
            updated_at=work_requirement.updated_at,
            lines=line_views,
        )
