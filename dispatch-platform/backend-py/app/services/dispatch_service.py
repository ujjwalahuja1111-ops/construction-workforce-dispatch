"""
DISPATCH + COMMITMENT — the vertical slice that turns Phase F's dispatch
*candidates* into actual dispatch *positions*, *offers*, and worker
*commitment*. See docs/Dispatch.md for the full writeup; this module's
docstring covers just the shape of what each method does.

    ELIGIBLE WORKERS (existing matching_service, reused, never bypassed)
        -> DISPATCH OFFER (one position, one worker, PENDING)
        -> WORKER ACCEPTS -> POSITION COMMITTED, OFFER ACCEPTED
                              competing offers for the same position CANCELLED
        -> WORKER DECLINES -> OFFER DECLINED, POSITION reopens (unless
                                already committed by a different offer)
        -> OFFER EXPIRES  -> same reopening, system-driven instead of
                              worker-driven
        -> REDISPATCH     -> the reopened position goes through dispatch
                              again, excluding whoever already
                              declined/expired for THIS position

Eligibility is never re-implemented here — `matching_service.eligible_workers`
(Phase E) is the single source of "who could do this work"; this module only
adds "who can we actually secure" on top: conflict exclusion (within- and
cross-work-requirement), and the offer/commitment transaction itself. No
ranking/scoring is introduced beyond what `eligible_workers` already
provides (deterministic level-desc/created-at-asc order) — "use
deterministic ordering," not a new scoring model.

Two-layer transition safety: `dispatch_state_machine.assert_*_transition`
validates that a transition is legal at all (using the status this service
just read, which can be stale under concurrency); the repository's
`try_transition` is the atomic, race-safe guard that actually applies it
(a single `UPDATE ... WHERE status = :expected` statement — see
SqlAlchemyDispatchPositionRepository.try_transition's docstring). Losing
the race there — not the state-machine check — is what makes TEST 8 (the
double-accept race) come out with exactly one winner: the loser's
`try_transition` call simply matches zero rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import AppError
from app.domain.entities import CrewRequirement, DispatchOffer, DispatchPosition, WorkRequirement
from app.domain.enums import FulfillmentStatus, OfferStatus, PositionStatus, Role
from app.domain.views import (
    CommittedAssignmentView,
    DispatchOfferView,
    DispatchSummaryView,
    ExpireOffersResultView,
    OfferActionResultView,
    PositionDispatchOutcomeView,
)
from app.repositories.sqlalchemy_repositories import (
    SqlAlchemyCrewRequirementRepository,
    SqlAlchemyDispatchOfferRepository,
    SqlAlchemyDispatchPositionRepository,
    SqlAlchemyTaskRepository,
    SqlAlchemyWorkerCapabilityRepository,
    SqlAlchemyWorkerRepository,
    SqlAlchemyWorkerSafetyQualificationRepository,
    SqlAlchemyWorkRequirementRepository,
)
from app.services import dispatch_state_machine, fulfillment, matching_service


def _utc_now() -> datetime:
    """Naive-UTC "now", matching what every datetime column reads back as
    on SQLite (the only dialect exercised by this test suite — SQLAlchemy's
    SQLite DATETIME type has no true tz-aware storage, so a value written
    as `datetime.now(UTC)` reads back with `tzinfo=None`, still the correct
    UTC instant). Comparing a naive DB-read value against an
    aware-`datetime.now(UTC)` raises TypeError; using this naive helper on
    both sides of every expiry/conflict comparison in this module sidesteps
    that without needing a custom SQLAlchemy TypeDecorator. On a
    genuinely tz-aware dialect (Postgres) this would need revisiting — see
    docs/Dispatch.md "Known limitations"."""
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True, slots=True)
class _PositionLine:
    position: DispatchPosition
    line: CrewRequirement


class DispatchService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self._db = db
        self._settings = settings
        self._work_requirements = SqlAlchemyWorkRequirementRepository(db)
        self._crew_requirements = SqlAlchemyCrewRequirementRepository(db)
        self._tasks = SqlAlchemyTaskRepository(db)
        self._workers = SqlAlchemyWorkerRepository(db)
        self._capabilities = SqlAlchemyWorkerCapabilityRepository(db)
        self._safety_qualifications = SqlAlchemyWorkerSafetyQualificationRepository(db)
        self._positions = SqlAlchemyDispatchPositionRepository(db)
        self._offers = SqlAlchemyDispatchOfferRepository(db)

    # ------------------------------------------------------------------
    # POST /api/work-requirements/{id}/dispatch
    # ------------------------------------------------------------------

    def dispatch(
        self, work_requirement_id: str, *, requesting_user_id: str, requesting_role: str
    ) -> DispatchSummaryView:
        work_requirement = self._work_requirements.get_by_id(work_requirement_id)
        if work_requirement is None:
            raise AppError.not_found("Work requirement not found")
        if requesting_role != Role.ADMIN and work_requirement.contractor_user_id != requesting_user_id:
            raise AppError.forbidden("You may only dispatch your own work requirements")

        lines = self._crew_requirements.list_for_work_requirement(work_requirement.id)
        lines_by_id = {line.id: line for line in lines}
        positions = self._positions.list_for_work_requirement(work_requirement.id)

        # Most-specialized-first, same priority order as
        # matching_service.assemble_crew — a harder-to-fill role gets first
        # pick of a shared eligible pool. Ties broken by line creation
        # order, then position index, so results are reproducible.
        ordered = sorted(
            (_PositionLine(position=p, line=lines_by_id[p.crew_requirement_id]) for p in positions),
            key=lambda pl: (-pl.line.min_level, pl.line.created_at, pl.position.position_index),
        )

        now = _utc_now()
        outcomes: list[PositionDispatchOutcomeView] = []
        for item in ordered:
            position, line = item.position, item.line
            if position.status in (
                PositionStatus.COMMITTED,
                PositionStatus.OFFERED,
                PositionStatus.CANCELLED,
            ):
                # COMMITTED: nothing to do. OFFERED: an offer is already
                # live for this position; dispatch never creates a second
                # one on top of it. CANCELLED: terminal, skip.
                outcomes.append(self._current_outcome(position, line))
                continue

            # position.status is OPEN or ESCALATED here.
            candidate_id = self._pick_candidate(work_requirement, line, position, now=now)
            if candidate_id is None:
                new_status = PositionStatus.ESCALATED
                if position.status == new_status:
                    # Already ESCALATED, still no candidate — a no-op, not
                    # a transition (ESCALATED -> ESCALATED isn't in the
                    # transition table on purpose: it isn't a real state
                    # change).
                    outcomes.append(self._current_outcome(position, line))
                    continue
                dispatch_state_machine.assert_position_transition(position.status, new_status)
                applied = self._positions.try_transition(
                    position.id,
                    expected_status=position.status,
                    new_status=new_status,
                    worker_id=None,
                )
                if not applied:
                    # Another concurrent dispatch call already moved this
                    # position on; re-read and report its current outcome
                    # rather than fighting the race.
                    refreshed = self._positions.get_by_id(position.id)
                    assert refreshed is not None
                    outcomes.append(self._current_outcome(refreshed, line))
                    continue
                outcomes.append(
                    PositionDispatchOutcomeView(
                        position_id=position.id,
                        crew_requirement_id=line.id,
                        task_code=self._task_code(line.task_id),
                        status=new_status,
                        offer=None,
                    )
                )
                continue

            new_status = PositionStatus.OFFERED
            dispatch_state_machine.assert_position_transition(position.status, new_status)
            expires_at = now + timedelta(minutes=self._settings.dispatch_offer_ttl_minutes)
            applied = self._positions.try_transition(
                position.id, expected_status=position.status, new_status=new_status, worker_id=None
            )
            if not applied:
                refreshed = self._positions.get_by_id(position.id)
                assert refreshed is not None
                outcomes.append(self._current_outcome(refreshed, line))
                continue
            offer = self._offers.create(
                position_id=position.id, worker_id=candidate_id, expires_at=expires_at
            )
            outcomes.append(
                PositionDispatchOutcomeView(
                    position_id=position.id,
                    crew_requirement_id=line.id,
                    task_code=self._task_code(line.task_id),
                    status=new_status,
                    offer=self._offer_view(offer, work_requirement.id, line.id),
                )
            )

        self._db.commit()
        return self._summarize(work_requirement.id, outcomes)

    def _pick_candidate(
        self,
        work_requirement: WorkRequirement,
        line: CrewRequirement,
        position: DispatchPosition,
        *,
        now: datetime,
    ) -> str | None:
        """Never bypasses eligibility (point 4): starts from the exact same
        `matching_service.eligible_workers` pool Phase E already produces,
        deterministically ordered, then narrows it with dispatch-specific
        exclusions (points 5-7 of the order)."""
        eligible = matching_service.eligible_workers(
            self._capabilities, self._safety_qualifications, work_requirement, line
        )

        excluded: set[str] = set()
        excluded |= self._offers.previously_declined_or_expired_worker_ids(position.id)
        excluded |= self._offers.pending_worker_ids_for_work_requirement(work_requirement.id, now=now)
        excluded |= {
            p.worker_id
            for p in self._positions.list_for_work_requirement(work_requirement.id)
            if p.status == PositionStatus.COMMITTED and p.worker_id
        }
        if work_requirement.requested_for is not None:
            excluded |= self._positions.committed_worker_ids_on_date(
                on_date=work_requirement.requested_for, exclude_work_requirement_id=work_requirement.id
            )
            excluded |= self._offers.pending_worker_ids_on_date(
                on_date=work_requirement.requested_for,
                exclude_work_requirement_id=work_requirement.id,
                now=now,
            )

        for candidate in eligible:
            if candidate.worker_id not in excluded:
                return candidate.worker_id
        return None

    def _current_outcome(
        self, position: DispatchPosition, line: CrewRequirement
    ) -> PositionDispatchOutcomeView:
        offer_view = None
        if position.status == PositionStatus.OFFERED:
            pending = [
                o for o in self._offers.list_for_position(position.id) if o.status == OfferStatus.PENDING
            ]
            if pending:
                offer_view = self._offer_view(pending[0], position.work_requirement_id, line.id)
        return PositionDispatchOutcomeView(
            position_id=position.id,
            crew_requirement_id=line.id,
            task_code=self._task_code(line.task_id),
            status=position.status,
            offer=offer_view,
        )

    def _task_code(self, task_id: str) -> str:
        task = self._tasks.get_by_id(task_id)
        assert task is not None
        return task.code

    def _offer_view(
        self, offer: DispatchOffer, work_requirement_id: str, crew_requirement_id: str
    ) -> DispatchOfferView:
        return DispatchOfferView(
            id=offer.id,
            position_id=offer.position_id,
            work_requirement_id=work_requirement_id,
            crew_requirement_id=crew_requirement_id,
            worker_id=offer.worker_id,
            status=offer.status,
            created_at=offer.created_at,
            expires_at=offer.expires_at,
            responded_at=offer.responded_at,
        )

    def _summarize(
        self, work_requirement_id: str, outcomes: list[PositionDispatchOutcomeView]
    ) -> DispatchSummaryView:
        positions = self._positions.list_for_work_requirement(work_requirement_id)
        lines = {
            line.id: line
            for line in self._crew_requirements.list_for_work_requirement(work_requirement_id)
        }
        committed = sum(1 for p in positions if p.status == PositionStatus.COMMITTED)
        open_count = sum(1 for p in positions if p.status == PositionStatus.OPEN)
        escalated = sum(1 for p in positions if p.status == PositionStatus.ESCALATED)
        pending_offers = self._offers.count_pending_for_positions([p.id for p in positions])

        line_statuses = []
        for line in lines.values():
            line_positions = [p for p in positions if p.crew_requirement_id == line.id]
            line_committed = sum(1 for p in line_positions if p.status == PositionStatus.COMMITTED)
            line_escalated = sum(1 for p in line_positions if p.status == PositionStatus.ESCALATED)
            line_statuses.append(
                fulfillment.dispatch_line_status(
                    committed_count=line_committed, escalated_count=line_escalated, quantity=line.quantity
                )
            )
        overall = fulfillment.overall_status(line_statuses) if line_statuses else FulfillmentStatus.ESCALATED

        return DispatchSummaryView(
            work_requirement_id=work_requirement_id,
            positions=outcomes,
            required_positions=len(positions),
            committed_positions=committed,
            open_positions=open_count,
            escalated_positions=escalated,
            pending_offers=pending_offers,
            dispatch_status=overall,
        )

    # ------------------------------------------------------------------
    # POST /api/dispatch/offers/{offer_id}/accept
    # ------------------------------------------------------------------

    def accept_offer(self, offer_id: str, *, requesting_user_id: str) -> CommittedAssignmentView:
        worker = self._workers.get_by_user_id(requesting_user_id)
        if worker is None:
            raise AppError.forbidden("No worker profile for this account")

        offer = self._offers.get_by_id(offer_id)
        if offer is None:
            raise AppError.not_found("Offer not found")
        if offer.worker_id != worker.id:
            raise AppError.forbidden("You may only accept your own offer")

        now = _utc_now()
        if offer.status != OfferStatus.PENDING:
            raise AppError.conflict(f"Offer is {offer.status.value}, not PENDING")

        if offer.expires_at <= now:
            self._lazily_expire(offer.id, offer.position_id)
            self._db.commit()
            raise AppError.conflict("Offer has expired")

        position = self._positions.get_by_id(offer.position_id)
        if position is None:
            raise AppError.not_found("Position not found")
        if position.status != PositionStatus.OFFERED:
            raise AppError.conflict(f"Position is {position.status.value}, not OFFERED")

        crew_requirement = self._crew_requirements.get_by_id(position.crew_requirement_id)
        if crew_requirement is None:
            raise AppError.not_found("Crew requirement not found")
        work_requirement = self._work_requirements.get_by_id(position.work_requirement_id)
        assert work_requirement is not None

        # Re-check every hard gate — nothing here trusts that conditions
        # from dispatch-time still hold (steps 4-6 of the accept order).
        capability = self._capabilities.get_by_worker_and_task(worker.id, crew_requirement.task_id)
        if capability is None or capability.level < crew_requirement.min_level:
            raise AppError.conflict("Worker no longer meets the required capability level")
        if not worker.is_available:
            raise AppError.conflict("Worker is no longer available")
        if crew_requirement.safety_qualification_required:
            qualified = self._safety_qualifications.has_qualification(worker.id, crew_requirement.task_id)
            if not qualified:
                raise AppError.conflict("Worker no longer holds the required safety qualification")
        if work_requirement.requested_for is not None:
            conflicting = self._positions.committed_worker_ids_on_date(
                on_date=work_requirement.requested_for, exclude_work_requirement_id=work_requirement.id
            )
            if worker.id in conflicting:
                raise AppError.conflict("Worker is already committed to a conflicting work requirement")

        dispatch_state_machine.assert_position_transition(position.status, PositionStatus.COMMITTED)
        applied = self._positions.try_transition(
            position.id,
            expected_status=PositionStatus.OFFERED,
            new_status=PositionStatus.COMMITTED,
            worker_id=worker.id,
        )
        if not applied:
            raise AppError.conflict("Position was already committed by another offer")

        dispatch_state_machine.assert_offer_transition(OfferStatus.PENDING, OfferStatus.ACCEPTED)
        offer_applied = self._offers.try_transition(
            offer.id, expected_status=OfferStatus.PENDING, new_status=OfferStatus.ACCEPTED, responded_at=now
        )
        if not offer_applied:
            # The position guard above already succeeded (this request IS
            # the winner), so this should be unreachable in practice; guard
            # anyway rather than trust it.
            raise AppError.conflict("Offer was already resolved")

        self._offers.cancel_other_pending_for_position(
            position.id, except_offer_id=offer.id, responded_at=now
        )
        self._db.commit()

        refreshed_wr = self._to_dispatch_status(work_requirement.id)
        return CommittedAssignmentView(
            position_id=position.id,
            work_requirement_id=work_requirement.id,
            crew_requirement_id=crew_requirement.id,
            worker_id=worker.id,
            offer_id=offer.id,
            committed_at=now,
            work_requirement_dispatch_status=refreshed_wr,
        )

    # ------------------------------------------------------------------
    # POST /api/dispatch/offers/{offer_id}/decline
    # ------------------------------------------------------------------

    def decline_offer(self, offer_id: str, *, requesting_user_id: str) -> OfferActionResultView:
        worker = self._workers.get_by_user_id(requesting_user_id)
        if worker is None:
            raise AppError.forbidden("No worker profile for this account")

        offer = self._offers.get_by_id(offer_id)
        if offer is None:
            raise AppError.not_found("Offer not found")
        if offer.worker_id != worker.id:
            raise AppError.forbidden("You may only decline your own offer")
        if offer.status != OfferStatus.PENDING:
            raise AppError.conflict(f"Offer is {offer.status.value}, not PENDING")

        now = _utc_now()
        dispatch_state_machine.assert_offer_transition(OfferStatus.PENDING, OfferStatus.DECLINED)
        applied = self._offers.try_transition(
            offer.id, expected_status=OfferStatus.PENDING, new_status=OfferStatus.DECLINED, responded_at=now
        )
        if not applied:
            raise AppError.conflict("Offer was already resolved")

        position = self._positions.get_by_id(offer.position_id)
        assert position is not None
        position_status = position.status
        if position.status == PositionStatus.OFFERED:
            # "Position -> OPEN unless another valid offer has already
            # committed the position" — reachable here means no one beat
            # this decline to COMMITTED (a position that's already
            # COMMITTED would not be OFFERED any more).
            dispatch_state_machine.assert_position_transition(position.status, PositionStatus.OPEN)
            if self._positions.try_transition(
                position.id,
                expected_status=PositionStatus.OFFERED,
                new_status=PositionStatus.OPEN,
                worker_id=None,
            ):
                position_status = PositionStatus.OPEN

        self._db.commit()
        return OfferActionResultView(
            offer_id=offer.id,
            position_id=position.id,
            offer_status=OfferStatus.DECLINED,
            position_status=position_status,
        )

    # ------------------------------------------------------------------
    # Expiry — deterministic, no background scheduler (see docs/Dispatch.md)
    # ------------------------------------------------------------------

    def expire_due_offers(self) -> ExpireOffersResultView:
        now = _utc_now()
        expired = self._offers.list_expired_pending(now=now)
        processed: list[OfferActionResultView] = []
        for offer in expired:
            processed.append(self._lazily_expire(offer.id, offer.position_id))
        self._db.commit()
        return ExpireOffersResultView(processed=processed)

    def _lazily_expire(self, offer_id: str, position_id: str) -> OfferActionResultView:
        dispatch_state_machine.assert_offer_transition(OfferStatus.PENDING, OfferStatus.EXPIRED)
        applied = self._offers.try_transition(
            offer_id,
            expected_status=OfferStatus.PENDING,
            new_status=OfferStatus.EXPIRED,
            responded_at=None,
        )
        position = self._positions.get_by_id(position_id)
        assert position is not None
        position_status = position.status
        if applied and position.status == PositionStatus.OFFERED:
            dispatch_state_machine.assert_position_transition(position.status, PositionStatus.OPEN)
            if self._positions.try_transition(
                position.id,
                expected_status=PositionStatus.OFFERED,
                new_status=PositionStatus.OPEN,
                worker_id=None,
            ):
                position_status = PositionStatus.OPEN
        return OfferActionResultView(
            offer_id=offer_id,
            position_id=position_id,
            offer_status=OfferStatus.EXPIRED,
            position_status=position_status,
        )

    def _to_dispatch_status(self, work_requirement_id: str) -> FulfillmentStatus:
        positions = self._positions.list_for_work_requirement(work_requirement_id)
        lines = self._crew_requirements.list_for_work_requirement(work_requirement_id)
        line_statuses = []
        for line in lines:
            line_positions = [p for p in positions if p.crew_requirement_id == line.id]
            committed = sum(1 for p in line_positions if p.status == PositionStatus.COMMITTED)
            escalated = sum(1 for p in line_positions if p.status == PositionStatus.ESCALATED)
            line_statuses.append(
                fulfillment.dispatch_line_status(
                    committed_count=committed, escalated_count=escalated, quantity=line.quantity
                )
            )
        return fulfillment.overall_status(line_statuses) if line_statuses else FulfillmentStatus.ESCALATED
