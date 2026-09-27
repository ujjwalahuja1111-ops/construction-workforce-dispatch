"""
SQLAlchemy implementations of the repository interfaces, and the ORM-row ->
domain-entity mappers. Nothing above the repository layer ever sees a
`*Model` (ORM) instance — only the framework-free entities from
app.domain.entities.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.domain.entities import (
    CrewRequirement,
    DispatchOffer,
    DispatchPosition,
    NewCrewRequirementLine,
    Shift,
    Task,
    Trade,
    Worker,
    WorkerCapability,
    WorkerSafetyQualification,
    WorkRequirement,
)
from app.domain.enums import AssessmentType, CapabilityProvenance, OfferStatus, PositionStatus, ShiftStatus
from app.domain.views import EligibleWorkerView, MyDispatchOfferView, WorkerCapabilityView
from app.infrastructure.db.models import (
    AssessmentModel,
    CrewRequirementModel,
    DispatchOfferModel,
    DispatchPositionModel,
    ShiftModel,
    TaskModel,
    TradeModel,
    WorkerCapabilityModel,
    WorkerModel,
    WorkerSafetyQualificationModel,
    WorkRequirementModel,
)


def _trade_to_entity(row: TradeModel) -> Trade:
    return Trade(
        id=row.id,
        code=row.code,
        name=row.name,
        description=row.description,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _task_to_entity(row: TaskModel) -> Task:
    return Task(
        id=row.id,
        trade_id=row.trade_id,
        code=row.code,
        name=row.name,
        description=row.description,
        safety_qualification_required=row.safety_qualification_required,
        adjacency_group=row.adjacency_group,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _worker_to_entity(row: WorkerModel) -> Worker:
    return Worker(
        id=row.id,
        user_id=row.user_id,
        city=row.city,
        state=row.state,
        legacy_skills_csv=row.legacy_skills_csv,
        is_available=row.is_available,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _work_requirement_to_entity(row: WorkRequirementModel) -> WorkRequirement:
    return WorkRequirement(
        id=row.id,
        contractor_user_id=row.contractor_user_id,
        city=row.city,
        state=row.state,
        requested_for=row.requested_for,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _crew_requirement_to_entity(row: CrewRequirementModel) -> CrewRequirement:
    return CrewRequirement(
        id=row.id,
        work_requirement_id=row.work_requirement_id,
        task_id=row.task_id,
        min_level=row.min_level,
        quantity=row.quantity,
        safety_qualification_required=row.safety_qualification_required,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _safety_qualification_to_entity(row: WorkerSafetyQualificationModel) -> WorkerSafetyQualification:
    return WorkerSafetyQualification(
        id=row.id,
        worker_id=row.worker_id,
        task_id=row.task_id,
        granted_at=row.granted_at,
        created_at=row.created_at,
    )


def _dispatch_position_to_entity(row: DispatchPositionModel) -> DispatchPosition:
    return DispatchPosition(
        id=row.id,
        work_requirement_id=row.work_requirement_id,
        crew_requirement_id=row.crew_requirement_id,
        position_index=row.position_index,
        worker_id=row.worker_id,
        status=PositionStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _dispatch_offer_to_entity(row: DispatchOfferModel) -> DispatchOffer:
    return DispatchOffer(
        id=row.id,
        position_id=row.position_id,
        worker_id=row.worker_id,
        status=OfferStatus(row.status),
        created_at=row.created_at,
        expires_at=row.expires_at,
        responded_at=row.responded_at,
    )


def _shift_to_entity(row: ShiftModel) -> Shift:
    return Shift(
        id=row.id,
        dispatch_position_id=row.dispatch_position_id,
        worker_id=row.worker_id,
        scheduled_for=row.scheduled_for,
        status=ShiftStatus(row.status),
        check_in_at=row.check_in_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _capability_to_entity(row: WorkerCapabilityModel) -> WorkerCapability:
    return WorkerCapability(
        id=row.id,
        worker_id=row.worker_id,
        task_id=row.task_id,
        level=row.level,
        provenance=CapabilityProvenance(row.provenance),
        confidence=row.confidence,
        restrictions=row.restrictions,
        evidence_ref=row.evidence_ref,
        last_verified_at=row.last_verified_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _capability_view_from_row(row: WorkerCapabilityModel) -> WorkerCapabilityView:
    """Requires `task` and `task.trade` to already be loaded on `row` (see
    the `joinedload` calls below) — never lazy-loads here, so this mapper
    never issues a query of its own."""
    return WorkerCapabilityView(
        id=row.id,
        worker_id=row.worker_id,
        task_id=row.task_id,
        level=row.level,
        provenance=CapabilityProvenance(row.provenance),
        created_at=row.created_at,
        updated_at=row.updated_at,
        task_code=row.task.code,
        task_name=row.task.name,
        trade_code=row.task.trade.code,
    )


_WITH_TASK_AND_TRADE = joinedload(WorkerCapabilityModel.task).joinedload(TaskModel.trade)


class SqlAlchemyTradeRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_active(self) -> list[Trade]:
        rows = self._db.execute(
            select(TradeModel).where(TradeModel.is_active.is_(True)).order_by(TradeModel.code)
        ).scalars()
        return [_trade_to_entity(r) for r in rows]

    def get_by_code(self, code: str) -> Trade | None:
        row = self._db.execute(select(TradeModel).where(TradeModel.code == code)).scalar_one_or_none()
        return _trade_to_entity(row) if row else None

    def get_by_id(self, trade_id: str) -> Trade | None:
        row = self._db.get(TradeModel, trade_id)
        return _trade_to_entity(row) if row else None


class SqlAlchemyTaskRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_code(self, code: str) -> Task | None:
        row = self._db.execute(select(TaskModel).where(TaskModel.code == code)).scalar_one_or_none()
        return _task_to_entity(row) if row else None

    def get_by_id(self, task_id: str) -> Task | None:
        row = self._db.get(TaskModel, task_id)
        return _task_to_entity(row) if row else None

    def list_by_trade(self, trade_id: str) -> list[Task]:
        rows = self._db.execute(
            select(TaskModel).where(TaskModel.trade_id == trade_id).order_by(TaskModel.code)
        ).scalars()
        return [_task_to_entity(r) for r in rows]


class SqlAlchemyWorkerRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_user_id(self, user_id: str) -> Worker | None:
        row = self._db.execute(
            select(WorkerModel).where(WorkerModel.user_id == user_id)
        ).scalar_one_or_none()
        return _worker_to_entity(row) if row else None


class SqlAlchemyWorkerCapabilityRepository:
    """
    The write side here (`create_self_declared` / `update_level_self_declared`)
    mirrors the TS backend's `CapabilityService.selfDeclare`: each writes the
    `WorkerCapability` row and its `Assessment` row, then commits once — a
    SQLAlchemy `Session` batches pending statements the same way Prisma's
    `$transaction` does, so both rows either land together or (on any
    exception before `commit()`) not at all; `get_db` rolls back on
    exception so a partial flush never lingers as an open transaction.

    The service layer is responsible for the case selection (create vs.
    update vs. 409-reject) — this repository only ever does what it's told;
    it does not itself decide whether a write is allowed.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_worker(self, worker_id: str) -> list[WorkerCapability]:
        rows = self._db.execute(
            select(WorkerCapabilityModel)
            .where(WorkerCapabilityModel.worker_id == worker_id)
            .order_by(WorkerCapabilityModel.created_at)
        ).scalars()
        return [_capability_to_entity(r) for r in rows]

    def get_by_worker_and_task(self, worker_id: str, task_id: str) -> WorkerCapability | None:
        row = self._db.execute(
            select(WorkerCapabilityModel).where(
                WorkerCapabilityModel.worker_id == worker_id,
                WorkerCapabilityModel.task_id == task_id,
            )
        ).scalar_one_or_none()
        return _capability_to_entity(row) if row else None

    def get_view_by_worker_and_task(self, worker_id: str, task_id: str) -> WorkerCapabilityView | None:
        row = self._db.execute(
            select(WorkerCapabilityModel)
            .options(_WITH_TASK_AND_TRADE)
            .where(
                WorkerCapabilityModel.worker_id == worker_id,
                WorkerCapabilityModel.task_id == task_id,
            )
        ).scalar_one_or_none()
        return _capability_view_from_row(row) if row else None

    def list_views_for_worker(self, worker_id: str) -> list[WorkerCapabilityView]:
        rows = self._db.execute(
            select(WorkerCapabilityModel)
            .options(_WITH_TASK_AND_TRADE)
            .where(WorkerCapabilityModel.worker_id == worker_id)
            .order_by(WorkerCapabilityModel.created_at)
        ).scalars()
        return [_capability_view_from_row(r) for r in rows]

    def list_capable_workers(self, task_id: str, min_level: int) -> list[EligibleWorkerView]:
        """Workers capable of `task_id` at >= `min_level`, restricted to
        `Worker.is_available` — task/level/availability are folded into one
        query since they're all plain columns on the two joined tables.
        Location and safety-qualification filtering happen in the service
        layer (app/services/matching_service.py), not here — see that
        module's docstring for why. Deterministically ordered (level desc,
        then created_at asc) so `MatchingService`'s ranking step is
        reproducible given the same data."""
        rows = self._db.execute(
            select(WorkerCapabilityModel)
            .join(WorkerModel, WorkerCapabilityModel.worker_id == WorkerModel.id)
            .options(joinedload(WorkerCapabilityModel.worker))
            .where(
                WorkerCapabilityModel.task_id == task_id,
                WorkerCapabilityModel.level >= min_level,
                WorkerModel.is_available.is_(True),
            )
            .order_by(WorkerCapabilityModel.level.desc(), WorkerCapabilityModel.created_at.asc())
        ).scalars()
        return [
            EligibleWorkerView(
                worker_id=r.worker_id,
                level=r.level,
                provenance=CapabilityProvenance(r.provenance),
                city=r.worker.city,
                state=r.worker.state,
            )
            for r in rows
        ]

    def create_self_declared(self, worker_id: str, task_id: str, level: int) -> WorkerCapabilityView:
        row = WorkerCapabilityModel(
            worker_id=worker_id,
            task_id=task_id,
            level=level,
            provenance=CapabilityProvenance.SELF_DECLARED.value,
        )
        self._db.add(row)
        self._db.flush()
        self._db.add(
            AssessmentModel(
                worker_capability_id=row.id,
                type=AssessmentType.SELF_DECLARATION.value,
                result=f"Self-declared level {level}",
                assessed_by=None,
            )
        )
        self._db.commit()
        view = self.get_view_by_worker_and_task(worker_id, task_id)
        assert view is not None  # just committed it; this cannot be None
        return view

    def update_level_self_declared(
        self, capability_id: str, old_level: int, new_level: int
    ) -> WorkerCapabilityView:
        row = self._db.get(WorkerCapabilityModel, capability_id)
        assert row is not None  # caller already resolved this row's id from the DB
        row.level = new_level
        self._db.flush()
        self._db.add(
            AssessmentModel(
                worker_capability_id=row.id,
                type=AssessmentType.SELF_DECLARATION.value,
                result=f"Self-declared level changed {old_level} → {new_level}",
                assessed_by=None,
            )
        )
        self._db.commit()
        view = self.get_view_by_worker_and_task(row.worker_id, row.task_id)
        assert view is not None
        return view


class SqlAlchemyWorkerSafetyQualificationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def has_qualification(self, worker_id: str, task_id: str) -> bool:
        row_id = self._db.execute(
            select(WorkerSafetyQualificationModel.id).where(
                WorkerSafetyQualificationModel.worker_id == worker_id,
                WorkerSafetyQualificationModel.task_id == task_id,
            )
        ).scalar_one_or_none()
        return row_id is not None

    def grant(self, worker_id: str, task_id: str) -> WorkerSafetyQualification:
        row = WorkerSafetyQualificationModel(worker_id=worker_id, task_id=task_id)
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return _safety_qualification_to_entity(row)


class SqlAlchemyWorkRequirementRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        contractor_user_id: str,
        city: str | None,
        state: str | None,
        requested_for: datetime | None,
        notes: str | None,
    ) -> WorkRequirement:
        row = WorkRequirementModel(
            contractor_user_id=contractor_user_id,
            city=city,
            state=state,
            requested_for=requested_for,
            notes=notes,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return _work_requirement_to_entity(row)

    def get_by_id(self, work_requirement_id: str) -> WorkRequirement | None:
        row = self._db.get(WorkRequirementModel, work_requirement_id)
        return _work_requirement_to_entity(row) if row else None


class SqlAlchemyCrewRequirementRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create_many(
        self, work_requirement_id: str, lines: list[NewCrewRequirementLine]
    ) -> list[CrewRequirement]:
        rows = [
            CrewRequirementModel(
                work_requirement_id=work_requirement_id,
                task_id=line.task_id,
                min_level=line.min_level,
                quantity=line.quantity,
                safety_qualification_required=line.safety_qualification_required,
            )
            for line in lines
        ]
        self._db.add_all(rows)
        self._db.commit()
        for row in rows:
            self._db.refresh(row)
        return [_crew_requirement_to_entity(r) for r in rows]

    def list_for_work_requirement(self, work_requirement_id: str) -> list[CrewRequirement]:
        rows = self._db.execute(
            select(CrewRequirementModel)
            .where(CrewRequirementModel.work_requirement_id == work_requirement_id)
            .order_by(CrewRequirementModel.created_at)
        ).scalars()
        return [_crew_requirement_to_entity(r) for r in rows]

    def get_by_id(self, crew_requirement_id: str) -> CrewRequirement | None:
        row = self._db.get(CrewRequirementModel, crew_requirement_id)
        return _crew_requirement_to_entity(row) if row else None


class SqlAlchemyDispatchPositionRepository:
    """Unlike the repositories above, the mutating methods here `flush()`
    rather than `commit()` — DispatchService owns the transaction boundary
    for a whole dispatch/accept/decline operation (position + offer(s)
    mutated together, one commit at the end), the same posture as the TS
    `ShiftService.transition`'s `prisma.$transaction(...)`. See
    docs/Dispatch.md "Two-layer transition safety"."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create_many_for_line(
        self, *, work_requirement_id: str, crew_requirement_id: str, quantity: int
    ) -> list[DispatchPosition]:
        rows = [
            DispatchPositionModel(
                work_requirement_id=work_requirement_id,
                crew_requirement_id=crew_requirement_id,
                position_index=i,
                status=PositionStatus.OPEN.value,
            )
            for i in range(quantity)
        ]
        self._db.add_all(rows)
        self._db.flush()
        return [_dispatch_position_to_entity(r) for r in rows]

    def list_for_work_requirement(self, work_requirement_id: str) -> list[DispatchPosition]:
        rows = self._db.execute(
            select(DispatchPositionModel)
            .where(DispatchPositionModel.work_requirement_id == work_requirement_id)
            .order_by(DispatchPositionModel.crew_requirement_id, DispatchPositionModel.position_index)
        ).scalars()
        return [_dispatch_position_to_entity(r) for r in rows]

    def list_for_crew_requirement(self, crew_requirement_id: str) -> list[DispatchPosition]:
        rows = self._db.execute(
            select(DispatchPositionModel)
            .where(DispatchPositionModel.crew_requirement_id == crew_requirement_id)
            .order_by(DispatchPositionModel.position_index)
        ).scalars()
        return [_dispatch_position_to_entity(r) for r in rows]

    def get_by_id(self, position_id: str) -> DispatchPosition | None:
        row = self._db.get(DispatchPositionModel, position_id)
        return _dispatch_position_to_entity(row) if row else None

    def try_transition(
        self,
        position_id: str,
        *,
        expected_status: PositionStatus,
        new_status: PositionStatus,
        worker_id: str | None,
    ) -> bool:
        """The atomic concurrency guard: a single `UPDATE ... WHERE id = :id
        AND status = :expected` statement. Whichever concurrent caller's
        UPDATE the database engine applies first wins; the loser's
        statement matches zero rows (the row no longer satisfies
        `status = :expected` once the winner's write lands) — this is what
        makes "exactly one succeeds" true even under genuine concurrent
        requests, not just careful Python-level sequencing. Returns
        whether THIS call's UPDATE was the one applied."""
        result = self._db.execute(
            update(DispatchPositionModel)
            .where(
                DispatchPositionModel.id == position_id,
                DispatchPositionModel.status == expected_status.value,
            )
            .values(status=new_status.value, worker_id=worker_id)
        )
        self._db.flush()
        return result.rowcount == 1

    def committed_worker_ids_on_date(
        self, *, on_date: datetime, exclude_work_requirement_id: str
    ) -> set[str]:
        """Cross-work-requirement conflict lookup — see docs/Dispatch.md
        "Cross-work-requirement conflicts: the V1 rule" for exactly what
        "on_date" means and what this deliberately does not attempt (no
        overlap/time-range reasoning, no calendar)."""
        rows = self._db.execute(
            select(DispatchPositionModel.worker_id, WorkRequirementModel.requested_for)
            .join(
                WorkRequirementModel,
                DispatchPositionModel.work_requirement_id == WorkRequirementModel.id,
            )
            .where(
                DispatchPositionModel.status == PositionStatus.COMMITTED.value,
                DispatchPositionModel.work_requirement_id != exclude_work_requirement_id,
                WorkRequirementModel.requested_for.is_not(None),
            )
        ).all()
        target = on_date.date()
        return {
            worker_id
            for worker_id, requested_for in rows
            if worker_id and requested_for.date() == target
        }


class SqlAlchemyDispatchOfferRepository:
    """See SqlAlchemyDispatchPositionRepository's docstring — mutating
    methods here `flush()`, not `commit()`, for the same reason."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, *, position_id: str, worker_id: str, expires_at: datetime) -> DispatchOffer:
        row = DispatchOfferModel(
            position_id=position_id,
            worker_id=worker_id,
            status=OfferStatus.PENDING.value,
            expires_at=expires_at,
        )
        self._db.add(row)
        self._db.flush()
        return _dispatch_offer_to_entity(row)

    def get_by_id(self, offer_id: str) -> DispatchOffer | None:
        row = self._db.get(DispatchOfferModel, offer_id)
        return _dispatch_offer_to_entity(row) if row else None

    def try_transition(
        self,
        offer_id: str,
        *,
        expected_status: OfferStatus,
        new_status: OfferStatus,
        responded_at: datetime | None,
    ) -> bool:
        result = self._db.execute(
            update(DispatchOfferModel)
            .where(DispatchOfferModel.id == offer_id, DispatchOfferModel.status == expected_status.value)
            .values(status=new_status.value, responded_at=responded_at)
        )
        self._db.flush()
        return result.rowcount == 1

    def cancel_other_pending_for_position(
        self, position_id: str, *, except_offer_id: str, responded_at: datetime
    ) -> list[DispatchOffer]:
        """"Competing offers: two workers have offers for one position; one
        accepts; the other offer becomes CANCELLED" (TEST 9) — called
        inside the same transaction as the winning accept, so a reader
        never observes a moment where the position is COMMITTED but a
        competing offer is still PENDING."""
        rows = self._db.execute(
            select(DispatchOfferModel).where(
                DispatchOfferModel.position_id == position_id,
                DispatchOfferModel.id != except_offer_id,
                DispatchOfferModel.status == OfferStatus.PENDING.value,
            )
        ).scalars().all()
        for row in rows:
            row.status = OfferStatus.CANCELLED.value
            row.responded_at = responded_at
        self._db.flush()
        return [_dispatch_offer_to_entity(r) for r in rows]

    def pending_worker_ids_for_work_requirement(
        self, work_requirement_id: str, *, now: datetime
    ) -> set[str]:
        """"Never offer the same worker twice for two positions within the
        same WorkRequirement" (point 7) — every worker who currently holds
        a live (PENDING, unexpired) offer anywhere in this WorkRequirement,
        so the dispatch loop can exclude them from a second position."""
        rows = self._db.execute(
            select(DispatchOfferModel.worker_id)
            .join(DispatchPositionModel, DispatchOfferModel.position_id == DispatchPositionModel.id)
            .where(
                DispatchPositionModel.work_requirement_id == work_requirement_id,
                DispatchOfferModel.status == OfferStatus.PENDING.value,
                DispatchOfferModel.expires_at > now,
            )
        ).scalars()
        return set(rows)

    def pending_worker_ids_on_date(
        self, *, on_date: datetime, exclude_work_requirement_id: str, now: datetime
    ) -> set[str]:
        """Cross-work-requirement counterpart to
        `pending_worker_ids_for_work_requirement` — a worker already
        holding a live offer for a conflicting date elsewhere must not
        receive a second one here."""
        rows = self._db.execute(
            select(DispatchOfferModel.worker_id, WorkRequirementModel.requested_for)
            .join(DispatchPositionModel, DispatchOfferModel.position_id == DispatchPositionModel.id)
            .join(
                WorkRequirementModel,
                DispatchPositionModel.work_requirement_id == WorkRequirementModel.id,
            )
            .where(
                DispatchOfferModel.status == OfferStatus.PENDING.value,
                DispatchOfferModel.expires_at > now,
                DispatchPositionModel.work_requirement_id != exclude_work_requirement_id,
                WorkRequirementModel.requested_for.is_not(None),
            )
        ).all()
        target = on_date.date()
        return {
            worker_id
            for worker_id, requested_for in rows
            if worker_id and requested_for.date() == target
        }

    def previously_declined_or_expired_worker_ids(self, position_id: str) -> set[str]:
        """"System must not repeatedly offer the same worker after they
        already declined/expired for that same position" — scoped to ONE
        position (a worker who declined position A of a 2-position line may
        still be validly offered position B)."""
        rows = self._db.execute(
            select(DispatchOfferModel.worker_id).where(
                DispatchOfferModel.position_id == position_id,
                DispatchOfferModel.status.in_([OfferStatus.DECLINED.value, OfferStatus.EXPIRED.value]),
            )
        ).scalars()
        return set(rows)

    def list_expired_pending(self, *, now: datetime) -> list[DispatchOffer]:
        rows = self._db.execute(
            select(DispatchOfferModel).where(
                DispatchOfferModel.status == OfferStatus.PENDING.value,
                DispatchOfferModel.expires_at <= now,
            )
        ).scalars()
        return [_dispatch_offer_to_entity(r) for r in rows]

    def count_pending_for_positions(self, position_ids: list[str]) -> int:
        if not position_ids:
            return 0
        rows = self._db.execute(
            select(DispatchOfferModel.id).where(
                DispatchOfferModel.position_id.in_(position_ids),
                DispatchOfferModel.status == OfferStatus.PENDING.value,
            )
        ).scalars().all()
        return len(rows)

    def list_for_position(self, position_id: str) -> list[DispatchOffer]:
        rows = self._db.execute(
            select(DispatchOfferModel)
            .where(DispatchOfferModel.position_id == position_id)
            .order_by(DispatchOfferModel.created_at)
        ).scalars()
        return [_dispatch_offer_to_entity(r) for r in rows]

    def list_for_worker(self, worker_id: str) -> list[MyDispatchOfferView]:
        """Backs `GET /api/dispatch/offers` — every offer (any status) ever
        made to this worker, most recent first, joined against the position/
        line/task/work-requirement it belongs to so the response is
        self-contained. Scoped to `worker_id` in the WHERE clause, not
        filtered after the fact — there is no code path here that could
        return another worker's offer."""
        rows = self._db.execute(
            select(
                DispatchOfferModel,
                DispatchPositionModel,
                CrewRequirementModel,
                TaskModel,
                WorkRequirementModel,
            )
            .join(DispatchPositionModel, DispatchOfferModel.position_id == DispatchPositionModel.id)
            .join(CrewRequirementModel, DispatchPositionModel.crew_requirement_id == CrewRequirementModel.id)
            .join(TaskModel, CrewRequirementModel.task_id == TaskModel.id)
            .join(WorkRequirementModel, DispatchPositionModel.work_requirement_id == WorkRequirementModel.id)
            .where(DispatchOfferModel.worker_id == worker_id)
            .order_by(DispatchOfferModel.created_at.desc())
        ).all()
        return [
            MyDispatchOfferView(
                id=offer.id,
                status=OfferStatus(offer.status),
                created_at=offer.created_at,
                expires_at=offer.expires_at,
                responded_at=offer.responded_at,
                position_id=position.id,
                work_requirement_id=position.work_requirement_id,
                crew_requirement_id=crew.id,
                task_code=task.code,
                task_name=task.name,
                min_level=crew.min_level,
                city=wr.city,
                state=wr.state,
                requested_for=wr.requested_for,
            )
            for offer, position, crew, task, wr in rows
        ]


class SqlAlchemyShiftRepository:
    """See SqlAlchemyDispatchPositionRepository's docstring for the
    flush-vs-commit convention — mutating methods here `flush()`, not
    `commit()`, so `ExecutionService` owns the transaction boundary
    (needed for the idempotent-creation IntegrityError handling — see
    app/services/execution_service.py)."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self, *, dispatch_position_id: str, worker_id: str, scheduled_for: datetime | None
    ) -> Shift:
        row = ShiftModel(
            dispatch_position_id=dispatch_position_id,
            worker_id=worker_id,
            scheduled_for=scheduled_for,
            status=ShiftStatus.SCHEDULED.value,
        )
        self._db.add(row)
        self._db.flush()
        return _shift_to_entity(row)

    def get_by_id(self, shift_id: str) -> Shift | None:
        row = self._db.get(ShiftModel, shift_id)
        return _shift_to_entity(row) if row else None

    def get_by_dispatch_position_id(self, dispatch_position_id: str) -> Shift | None:
        row = self._db.execute(
            select(ShiftModel).where(ShiftModel.dispatch_position_id == dispatch_position_id)
        ).scalar_one_or_none()
        return _shift_to_entity(row) if row else None

    def try_transition(
        self,
        shift_id: str,
        *,
        expected_status: ShiftStatus,
        new_status: ShiftStatus,
        check_in_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> bool:
        """Same atomic-guard pattern as the dispatch position/offer
        repositories: a single `UPDATE ... WHERE status = :expected`
        statement — see docs/Dispatch.md "Two-layer transition safety"."""
        values: dict[str, object] = {"status": new_status.value}
        if check_in_at is not None:
            values["check_in_at"] = check_in_at
        if completed_at is not None:
            values["completed_at"] = completed_at
        result = self._db.execute(
            update(ShiftModel)
            .where(ShiftModel.id == shift_id, ShiftModel.status == expected_status.value)
            .values(**values)
        )
        self._db.flush()
        return result.rowcount == 1
