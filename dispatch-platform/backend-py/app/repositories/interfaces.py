"""
Repository interfaces (structural typing via Protocol). Services/routes
depend on these, never on SQLAlchemy directly — the concrete implementation
in sqlalchemy_repositories.py is an infrastructure detail that can be swapped
(e.g. for a test double) without touching anything above this layer.

Only the read/lookup operations this foundation patch actually needs. Write
paths for WorkerCapability/Assessment (the self-declare flow, mirroring the
TS backend's CapabilityService.selfDeclare) are the natural next patch, not
this one — see docs/PythonMigration.md.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.entities import Task, Trade, Worker, WorkerCapability


class TradeRepository(Protocol):
    def list_active(self) -> list[Trade]: ...
    def get_by_code(self, code: str) -> Trade | None: ...


class TaskRepository(Protocol):
    def get_by_code(self, code: str) -> Task | None: ...
    def list_by_trade(self, trade_id: str) -> list[Task]: ...


class WorkerRepository(Protocol):
    def get_by_user_id(self, user_id: str) -> Worker | None: ...


class WorkerCapabilityRepository(Protocol):
    def list_for_worker(self, worker_id: str) -> list[WorkerCapability]: ...
