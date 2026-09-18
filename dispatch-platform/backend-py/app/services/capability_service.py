"""
Application/service layer for worker capability self-declaration — the
Python port of the TS backend's `CapabilityService.selfDeclare` /
`listForAuthenticatedWorker` (backend/src/services/capability.service.ts).

Same three-case logic, same reasoning, ported deliberately rather than
translated line-by-line:

  1. No existing (worker, task) row       -> create, provenance
     SELF_DECLARED, + one Assessment(SELF_DECLARATION). `created = True`.
  2. Existing row, still SELF_DECLARED    -> update `level` in place on the
     SAME row + append a new Assessment(SELF_DECLARATION). `created = False`.
  3. Existing row, provenance has moved   -> reject. Nothing is written —
     beyond SELF_DECLARED                   not even an Assessment row.

Case 3 is the only place provenance accuracy is protected; case 2's
in-place update is safe precisely because it can only run while nothing has
been verified yet — identical reasoning to the TS implementation and to the
approved Patch 2 contract (patch2-contract-v2.md §7/§8).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.enums import CapabilityProvenance
from app.domain.views import WorkerCapabilityView
from app.repositories.sqlalchemy_repositories import (
    SqlAlchemyTaskRepository,
    SqlAlchemyWorkerCapabilityRepository,
    SqlAlchemyWorkerRepository,
)


class CapabilityService:
    def __init__(self, db: Session) -> None:
        self._workers = SqlAlchemyWorkerRepository(db)
        self._tasks = SqlAlchemyTaskRepository(db)
        self._capabilities = SqlAlchemyWorkerCapabilityRepository(db)

    def self_declare(
        self, worker_user_id: str, task_id: str, level: int
    ) -> tuple[WorkerCapabilityView, bool]:
        worker = self._workers.get_by_user_id(worker_user_id)
        if worker is None:
            raise AppError.not_found("Worker profile not found")

        task = self._tasks.get_by_id(task_id)
        if task is None or not task.is_active:
            raise AppError.not_found("Task not found")

        existing = self._capabilities.get_by_worker_and_task(worker.id, task_id)

        if existing is not None and existing.provenance != CapabilityProvenance.SELF_DECLARED:
            raise AppError.conflict(
                "This capability has already been assessed and cannot be changed by self-declaration"
            )

        if existing is not None:
            view = self._capabilities.update_level_self_declared(existing.id, existing.level, level)
            return view, False

        view = self._capabilities.create_self_declared(worker.id, task_id, level)
        return view, True

    def list_for_authenticated_worker(self, worker_user_id: str) -> list[WorkerCapabilityView]:
        worker = self._workers.get_by_user_id(worker_user_id)
        if worker is None:
            raise AppError.not_found("Worker profile not found")
        return self._capabilities.list_views_for_worker(worker.id)
