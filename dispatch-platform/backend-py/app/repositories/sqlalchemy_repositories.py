"""
SQLAlchemy implementations of the repository interfaces, and the ORM-row ->
domain-entity mappers. Nothing above the repository layer ever sees a
`*Model` (ORM) instance — only the framework-free entities from
app.domain.entities.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities import Task, Trade, Worker, WorkerCapability
from app.domain.enums import CapabilityProvenance
from app.infrastructure.db.models import TaskModel, TradeModel, WorkerCapabilityModel, WorkerModel


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


class SqlAlchemyTaskRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_code(self, code: str) -> Task | None:
        row = self._db.execute(select(TaskModel).where(TaskModel.code == code)).scalar_one_or_none()
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
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_worker(self, worker_id: str) -> list[WorkerCapability]:
        rows = self._db.execute(
            select(WorkerCapabilityModel)
            .where(WorkerCapabilityModel.worker_id == worker_id)
            .order_by(WorkerCapabilityModel.created_at)
        ).scalars()
        return [_capability_to_entity(r) for r in rows]
