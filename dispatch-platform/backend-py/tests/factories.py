"""
Shared test factories for the worker-capability HTTP test suite — the
Python port of backend/tests/helpers.ts (`createWorker()`/`authHeader()`)
plus a seed for the frozen V1 taxonomy (backend/prisma/seeds/taxonomy.ts),
kept here as test-only fixtures: this patch does not add a taxonomy admin
endpoint or a standalone seed script on the Python side, so there is no
production code that needs this list yet (see docs/PythonMigration.md).

NOTE: the approved V1 taxonomy is 3 Trades / 11 Tasks (4 under MASONRY, 4
under ELECTRICAL, 3 under PLUMBING) — byte-for-byte the same codes/names as
the TS seed, which is the authoritative list. Do not add a 12th task here.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings
from app.infrastructure.db.models import TaskModel, TradeModel, UserModel, WorkerModel
from app.infrastructure.security.jwt import create_access_token


@dataclass(frozen=True, slots=True)
class _TaskSeed:
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class _TradeSeed:
    code: str
    name: str
    tasks: tuple[_TaskSeed, ...]


V1_TAXONOMY: tuple[_TradeSeed, ...] = (
    _TradeSeed(
        code="MASONRY",
        name="Masonry",
        tasks=(
            _TaskSeed("BRICKWORK_NEW_WALL", "Brickwork - New Wall"),
            _TaskSeed("BRICKWORK_REPAIR", "Brickwork - Repair"),
            _TaskSeed("BLOCKWORK", "Blockwork"),
            _TaskSeed("PLASTER", "Plaster"),
        ),
    ),
    _TradeSeed(
        code="ELECTRICAL",
        name="Electrical",
        tasks=(
            _TaskSeed("FAN_INSTALLATION", "Fan Installation"),
            _TaskSeed("LIGHT_INSTALLATION", "Light Installation"),
            _TaskSeed("WIRING", "Wiring"),
            _TaskSeed("FAULT_FINDING", "Fault Finding"),
        ),
    ),
    _TradeSeed(
        code="PLUMBING",
        name="Plumbing",
        tasks=(
            _TaskSeed("LEAKAGE_REPAIR", "Leakage Repair"),
            _TaskSeed("PIPE_INSTALLATION", "Pipe Installation"),
            _TaskSeed("BATHROOM_PLUMBING", "Bathroom Plumbing"),
        ),
    ),
)


def seed_taxonomy(db: Session) -> dict[str, TaskModel]:
    """Inserts the full V1 taxonomy and returns a {task_code: TaskModel}
    lookup. Each test's `db_session` is a fresh in-memory database (see
    conftest.py), so this never collides with a prior test's rows — no
    upsert-by-code needed here, unlike the TS seed which runs against a
    shared dev database."""
    tasks_by_code: dict[str, TaskModel] = {}
    for trade in V1_TAXONOMY:
        trade_row = TradeModel(code=trade.code, name=trade.name)
        db.add(trade_row)
        db.flush()
        for task in trade.tasks:
            task_row = TaskModel(trade_id=trade_row.id, code=task.code, name=task.name)
            db.add(task_row)
            db.flush()
            tasks_by_code[task.code] = task_row
    db.commit()
    return tasks_by_code


_phone_counter = 0


@dataclass(slots=True)
class CreatedWorker:
    user: UserModel
    worker: WorkerModel


def create_worker(
    db: Session,
    *,
    skills: str | None = "MASON,HELPER",
    city: str = "Bengaluru",
    state: str = "Karnataka",
) -> CreatedWorker:
    """Creates a real User+Worker pair directly via the ORM, mirroring
    helpers.ts#createWorker(). A fresh phone number per call, scoped to the
    module (each test gets its own in-memory DB, so global counter reuse
    across tests is harmless)."""
    global _phone_counter
    _phone_counter += 1
    user = UserModel(
        phone=f"+9199{1000000 + _phone_counter:07d}",
        role="WORKER",
        full_name=f"Test Worker {_phone_counter}",
        is_verified=True,
    )
    db.add(user)
    db.flush()
    worker = WorkerModel(user_id=user.id, legacy_skills_csv=skills, city=city, state=state)
    db.add(worker)
    db.commit()
    return CreatedWorker(user=user, worker=worker)


def auth_header(*, user_id: str, role: str, phone: str, settings: Settings) -> dict[str, str]:
    """Signs a token with the same shape TokenPayload expects and returns a
    ready-to-use Authorization header dict. For a role-mismatch (403) test
    there is no need for a real User row — require_role rejects on the
    token's `role` claim before any DB lookup happens — so callers may pass
    a synthetic id/role/phone rather than a row from create_worker()."""
    token = create_access_token({"sub": user_id, "role": role, "phone": phone}, settings)
    return {"Authorization": f"Bearer {token}"}
