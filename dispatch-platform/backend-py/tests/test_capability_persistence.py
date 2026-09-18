"""
Persistence checks for the capability model this foundation patch ports:
Trade -> Task -> WorkerCapability -> Assessment, through the repository
layer (never touching ORM rows directly from a test, same discipline the
application code follows).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.domain.enums import AssessmentType, CapabilityProvenance
from app.infrastructure.db.models import (
    AssessmentModel,
    TaskModel,
    TradeModel,
    UserModel,
    WorkerCapabilityModel,
    WorkerModel,
)
from app.repositories.sqlalchemy_repositories import (
    SqlAlchemyTaskRepository,
    SqlAlchemyTradeRepository,
    SqlAlchemyWorkerCapabilityRepository,
    SqlAlchemyWorkerRepository,
)


def _seed_worker(db: Session) -> WorkerModel:
    user = UserModel(phone="+919990000001", role="WORKER", full_name="Test Worker", is_verified=True)
    db.add(user)
    db.flush()
    worker = WorkerModel(user_id=user.id, city="Bengaluru", state="Karnataka")
    db.add(worker)
    db.flush()
    return worker


def _seed_taxonomy(db: Session) -> TaskModel:
    trade = TradeModel(code="MASONRY", name="Masonry")
    db.add(trade)
    db.flush()
    task = TaskModel(trade_id=trade.id, code="BRICKWORK_NEW_WALL", name="Brickwork - New Wall")
    db.add(task)
    db.flush()
    return task


def test_trade_and_task_repositories_round_trip(db_session: Session) -> None:
    task = _seed_taxonomy(db_session)
    db_session.commit()

    trades = SqlAlchemyTradeRepository(db_session).list_active()
    assert [t.code for t in trades] == ["MASONRY"]

    trade = SqlAlchemyTradeRepository(db_session).get_by_code("MASONRY")
    assert trade is not None and trade.id == task.trade_id

    fetched_task = SqlAlchemyTaskRepository(db_session).get_by_code("BRICKWORK_NEW_WALL")
    assert fetched_task is not None
    assert fetched_task.id == task.id

    tasks_for_trade = SqlAlchemyTaskRepository(db_session).list_by_trade(task.trade_id)
    assert [t.code for t in tasks_for_trade] == ["BRICKWORK_NEW_WALL"]


def test_worker_repository_resolves_by_user_id(db_session: Session) -> None:
    worker = _seed_worker(db_session)
    db_session.commit()

    resolved = SqlAlchemyWorkerRepository(db_session).get_by_user_id(worker.user_id)
    assert resolved is not None
    assert resolved.id == worker.id


def test_worker_capability_and_assessment_persist_and_round_trip(db_session: Session) -> None:
    worker = _seed_worker(db_session)
    task = _seed_taxonomy(db_session)

    capability = WorkerCapabilityModel(
        worker_id=worker.id,
        task_id=task.id,
        level=2,
        provenance=CapabilityProvenance.SELF_DECLARED.value,
    )
    db_session.add(capability)
    db_session.flush()

    assessment = AssessmentModel(
        worker_capability_id=capability.id,
        type=AssessmentType.SELF_DECLARATION.value,
        result="Self-declared level 2",
        assessed_by=None,
        assessed_at=datetime.now(UTC),
    )
    db_session.add(assessment)
    db_session.commit()

    capabilities = SqlAlchemyWorkerCapabilityRepository(db_session).list_for_worker(worker.id)
    assert len(capabilities) == 1
    assert capabilities[0].level == 2
    assert capabilities[0].provenance == CapabilityProvenance.SELF_DECLARED
    assert capabilities[0].task_id == task.id

    # unique(worker_id, task_id) is enforced at the DB layer, same as
    # Prisma's @@unique(workerId, taskId) on WorkerCapability.
    dup = WorkerCapabilityModel(
        worker_id=worker.id,
        task_id=task.id,
        level=3,
        provenance=CapabilityProvenance.SELF_DECLARED.value,
    )
    db_session.add(dup)
    try:
        db_session.commit()
        raised = False
    except Exception:  # noqa: BLE001 - asserting *some* integrity error, not a specific driver exception
        db_session.rollback()
        raised = True
    assert raised, "expected a UNIQUE constraint violation on (worker_id, task_id)"
