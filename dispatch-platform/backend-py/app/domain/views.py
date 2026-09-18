"""
Read-side view models: shapes assembled for a specific query/response, as
opposed to app.domain.entities (write-side aggregates). WorkerCapabilityView
carries the joined Task/Trade fields the API response needs (code, name,
tradeCode) without polluting the WorkerCapability entity itself with data
that belongs to a different aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import CapabilityProvenance


@dataclass(slots=True)
class WorkerCapabilityView:
    id: str
    worker_id: str
    task_id: str
    level: int
    provenance: CapabilityProvenance
    created_at: datetime
    updated_at: datetime
    task_code: str
    task_name: str
    trade_code: str
