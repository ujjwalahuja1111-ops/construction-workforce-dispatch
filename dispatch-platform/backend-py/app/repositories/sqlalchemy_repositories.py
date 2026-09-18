"""
SQLAlchemy implementations of the repository interfaces, and the ORM-row ->
domain-entity mappers. Nothing above the repository layer ever sees a
`*Model` (ORM) instance — only the framework-free entities from
app.domain.entities.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.domain.entities import (
    CrewRequirement,
    NewCrewRequirementLine,
    Task,
    Trade,
    Worker,
    WorkerCapability,
    WorkerSafetyQualification,
    WorkRequirement,
)
from app.domain.enums import AssessmentType, CapabilityProvenance
from app.domain.views import EligibleWorkerView, WorkerCapabilityView
from app.infrastructure.db.models import (
    AssessmentModel,
    CrewRequirementModel,
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
