"""
Deterministic development/test seed — the minimum data needed to execute the
full CONTRACTOR -> WORK REQUIREMENT -> DISPATCH -> OFFER -> ACCEPT ->
EXECUTION -> CHECK-IN -> START -> COMPLETE product journey against a running
`backend-py` instance, plus ready-to-use bearer tokens for the two seeded
accounts.

This is a DEV-ONLY TOOL, not production business logic and not a second
authentication architecture: backend-py has no phone+OTP issuance endpoint
of its own yet (see docs/PythonMigration.md "Retirement plan" — auth
*verification* is ported, auth *issuance* is not), so there is currently no
way to "log in" over HTTP at all. This script closes that gap the same way
the test suite already does (tests/factories.py:auth_header) — by calling
the exact same `create_access_token` function the app itself verifies
against, with the same JWT_SECRET/algorithm from Settings. It introduces no
new runtime code path in the app: nothing here is reachable over HTTP.

Idempotent and safe to re-run: every row is looked up by its natural key
(phone for users, code for trade/task, (worker, task) for capability)
before creating anything, mirroring the existing TS seed's own idempotency
convention (backend/prisma/seeds/taxonomy.ts) and the exact same tables
tests/factories.py already seeds for the test suite — deliberately not a
new taxonomy, not a new fixture shape, and not a large fake dataset: one
trade, one task, one contractor, one worker.

Usage (from backend-py/, with the venv active and `alembic upgrade head`
already run against DATABASE_URL):

    python -m scripts.dev_seed

Refuses to run when NODE_ENV=production, and refuses (with a clear message)
if the expected tables don't exist yet rather than silently creating a
schema that bypasses Alembic.
"""

from __future__ import annotations

import sys

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.infrastructure.db.models import (
    TaskModel,
    TradeModel,
    UserModel,
    WorkerCapabilityModel,
    WorkerModel,
)
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.security.jwt import create_access_token
from app.repositories.sqlalchemy_repositories import SqlAlchemyWorkerCapabilityRepository

# Deterministic, fixed dev-only identifiers — re-running this script never
# produces a second copy of any of these rows.
CONTRACTOR_PHONE = "+910000000001"
WORKER_PHONE = "+910000000002"
TRADE_CODE = "MASONRY"
TASK_CODE = "BRICKWORK_NEW_WALL"
WORKER_CITY = "Bengaluru"
WORKER_STATE = "Karnataka"
WORKER_CAPABILITY_LEVEL = 3  # matches the task's default min_level in the walkthrough


def _get_or_create_user(db: Session, *, phone: str, role: str, full_name: str) -> UserModel:
    existing = db.execute(select(UserModel).where(UserModel.phone == phone)).scalar_one_or_none()
    if existing is not None:
        return existing
    user = UserModel(phone=phone, role=role, full_name=full_name, is_verified=True)
    db.add(user)
    db.flush()
    return user


def _get_or_create_trade(db: Session) -> TradeModel:
    existing = db.execute(select(TradeModel).where(TradeModel.code == TRADE_CODE)).scalar_one_or_none()
    if existing is not None:
        return existing
    trade = TradeModel(code=TRADE_CODE, name="Masonry")
    db.add(trade)
    db.flush()
    return trade


def _get_or_create_task(db: Session, trade: TradeModel) -> TaskModel:
    existing = db.execute(select(TaskModel).where(TaskModel.code == TASK_CODE)).scalar_one_or_none()
    if existing is not None:
        return existing
    task = TaskModel(trade_id=trade.id, code=TASK_CODE, name="Brickwork - New Wall")
    db.add(task)
    db.flush()
    return task


def _get_or_create_worker(db: Session, user: UserModel) -> WorkerModel:
    existing = db.execute(select(WorkerModel).where(WorkerModel.user_id == user.id)).scalar_one_or_none()
    if existing is not None:
        return existing
    worker = WorkerModel(user_id=user.id, city=WORKER_CITY, state=WORKER_STATE, is_available=True)
    db.add(worker)
    db.flush()
    return worker


def _ensure_capability(db: Session, worker: WorkerModel, task: TaskModel) -> None:
    existing = db.execute(
        select(WorkerCapabilityModel).where(
            WorkerCapabilityModel.worker_id == worker.id, WorkerCapabilityModel.task_id == task.id
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    # Goes through the real self-declare repository method (not a raw
    # insert) so the same Assessment row a genuine self-declaration would
    # produce exists here too — this is real application data, not a
    # shortcut around it.
    SqlAlchemyWorkerCapabilityRepository(db).create_self_declared(
        worker.id, task.id, WORKER_CAPABILITY_LEVEL
    )


def main() -> int:
    settings = get_settings()
    if settings.node_env == "production":
        print("Refusing to run: NODE_ENV=production. This script is dev/test-only.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        try:
            db.execute(select(UserModel.id).limit(1))
        except OperationalError:
            print(
                "Database schema not found. Run `alembic upgrade head` first "
                f"(DATABASE_URL={settings.database_url}).",
                file=sys.stderr,
            )
            return 1

        contractor_user = _get_or_create_user(
            db, phone=CONTRACTOR_PHONE, role="CONTRACTOR", full_name="Dev Contractor"
        )
        worker_user = _get_or_create_user(db, phone=WORKER_PHONE, role="WORKER", full_name="Dev Worker")
        worker = _get_or_create_worker(db, worker_user)
        trade = _get_or_create_trade(db)
        task = _get_or_create_task(db, trade)
        _ensure_capability(db, worker, task)
        db.commit()

        # Capture everything printed below as plain values while the
        # session is still open — accessing an ORM attribute after
        # `db.close()` raises DetachedInstanceError once commit() has
        # expired the instance's loaded state.
        trade_code, trade_id = trade.code, trade.id
        task_code, task_id = task.code, task.id
        contractor_user_id, contractor_phone = contractor_user.id, contractor_user.phone
        worker_user_id, worker_phone = worker_user.id, worker_user.phone
        worker_id = worker.id

        contractor_token = create_access_token(
            {"sub": contractor_user_id, "role": "CONTRACTOR", "phone": contractor_phone}, settings
        )
        worker_token = create_access_token(
            {"sub": worker_user_id, "role": "WORKER", "phone": worker_phone}, settings
        )
    finally:
        db.close()

    print("Seeded (idempotent — safe to re-run):")
    print(f"  Trade:               {trade_code} ({trade_id})")
    print(f"  Task:                {task_code} ({task_id})")
    print(f"  Contractor user id:  {contractor_user_id}")
    print(f"  Worker user id:      {worker_user_id}")
    print(f"  Worker id:           {worker_id}  (capability: L{WORKER_CAPABILITY_LEVEL} {task_code})")
    print()
    print("Bearer tokens (see docs/ProductTestGuide.md for the full curl walkthrough):")
    print()
    print(f"CONTRACTOR_TOKEN={contractor_token}")
    print(f"WORKER_TOKEN={worker_token}")
    print(f"TASK_ID={task_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
