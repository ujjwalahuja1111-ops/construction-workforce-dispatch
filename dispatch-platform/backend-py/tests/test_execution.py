"""
End-to-end product tests for "COMMITTED POSITION -> MINIMAL SHIFT /
EXECUTION" — the vertical slice that turns a COMMITTED DispatchPosition
into an actual work assignment a worker can check into, work, and complete:

    COMMITTED DispatchPosition -> CREATE EXECUTION -> CHECK-IN -> START
        -> COMPLETE

Every request goes through the real FastAPI app (`client` fixture), same
discipline as test_dispatch.py. Covers all 20 required scenarios from the
CTO order plus the end-to-end integration test.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.enums import PositionStatus
from app.infrastructure.db.models import DispatchPositionModel, ShiftModel, TaskModel
from tests.factories import (
    CreatedWorker,
    auth_header,
    create_contractor,
    create_worker,
    grant_capability,
    seed_taxonomy,
)

WORK_REQS = "/api/work-requirements"
OFFERS = "/api/dispatch/offers"
POSITIONS = "/api/dispatch-positions"
EXECUTIONS = "/api/executions"


def _contractor_auth(db: Session, settings: Settings) -> tuple[str, dict[str, str]]:
    contractor = create_contractor(db)
    headers = auth_header(
        user_id=contractor.user.id, role="CONTRACTOR", phone=contractor.user.phone, settings=settings
    )
    return contractor.user.id, headers


def _worker_auth(worker: CreatedWorker, settings: Settings) -> dict[str, str]:
    return auth_header(user_id=worker.user.id, role="WORKER", phone=worker.user.phone, settings=settings)


def _mason_request(tasks: dict[str, TaskModel], *, requested_for: str | None = None) -> dict[str, object]:
    brickwork_id = tasks["BRICKWORK_NEW_WALL"].id
    payload: dict[str, object] = {
        "city": "Bengaluru",
        "state": "Karnataka",
        "lines": [{"taskId": brickwork_id, "minLevel": 3, "quantity": 1}],
    }
    if requested_for is not None:
        payload["requestedFor"] = requested_for
    return payload


def _committed_position(
    client: TestClient,
    db_session: Session,
    test_settings: Settings,
    *,
    requested_for: str | None = None,
) -> tuple[str, str, CreatedWorker, dict[str, str], dict[str, str]]:
    """Drives the full pre-existing dispatch flow (create -> dispatch ->
    accept) to arrive at exactly one COMMITTED DispatchPosition — the
    precondition every execution test starts from. Returns
    (work_requirement_id, position_id, worker, contractor_headers,
    worker_headers)."""
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)

    worker = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=worker.worker.id, task_id=task.id, level=3)

    create_res = client.post(
        WORK_REQS, json=_mason_request(tasks, requested_for=requested_for), headers=contractor_headers
    )
    assert create_res.status_code == 201
    wr = create_res.json()

    dispatch_res = client.post(f"{WORK_REQS}/{wr['id']}/dispatch", headers=contractor_headers)
    assert dispatch_res.status_code == 200
    (position,) = dispatch_res.json()["positions"]
    offer = position["offer"]
    assert offer is not None

    worker_headers = _worker_auth(worker, test_settings)
    accept_res = client.post(f"{OFFERS}/{offer['id']}/accept", headers=worker_headers)
    assert accept_res.status_code == 200

    return wr["id"], position["positionId"], worker, contractor_headers, worker_headers


def _create_execution(client: TestClient, headers: dict[str, str], position_id: str) -> Any:
    res = client.post(f"{POSITIONS}/{position_id}/execution", headers=headers)
    assert res.status_code in (200, 201), res.text
    return res


# ---------------------------------------------------------------------------
# 1. COMMITTED position can create execution.
# ---------------------------------------------------------------------------
def test_committed_position_can_create_execution(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    _, position_id, worker, contractor_headers, _ = _committed_position(client, db_session, test_settings)

    res = _create_execution(client, contractor_headers, position_id)
    assert res.status_code == 201
    body = res.json()
    assert body["dispatchPositionId"] == position_id
    assert body["workerId"] == worker.worker.id
    assert body["status"] == "SCHEDULED"
    assert body["checkInAt"] is None
    assert body["completedAt"] is None


# ---------------------------------------------------------------------------
# 2-5. Only a COMMITTED position may produce an execution.
# ---------------------------------------------------------------------------
def test_open_position_cannot_create_execution(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    _, contractor_headers = _contractor_auth(db_session, test_settings)
    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=contractor_headers)
    wr = create_res.json()
    # Not yet dispatched at all -> the position is still OPEN. Positions
    # aren't exposed on the WorkRequirement read view, so fetch the id via
    # the DB purely to target this specific status for the test.
    row = db_session.query(DispatchPositionModel).filter_by(work_requirement_id=wr["id"]).one()
    assert row.status == PositionStatus.OPEN.value
    res = client.post(f"{POSITIONS}/{row.id}/execution", headers=contractor_headers)
    assert res.status_code == 409, res.text


def test_offered_position_cannot_create_execution(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)
    worker = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=worker.worker.id, task_id=task.id, level=3)

    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=contractor_headers)
    wr = create_res.json()
    dispatch_res = client.post(f"{WORK_REQS}/{wr['id']}/dispatch", headers=contractor_headers)
    (position,) = dispatch_res.json()["positions"]
    assert position["status"] == "OFFERED"

    res = client.post(f"{POSITIONS}/{position['positionId']}/execution", headers=contractor_headers)
    assert res.status_code == 409, res.text


def test_escalated_position_cannot_create_execution(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    _, contractor_headers = _contractor_auth(db_session, test_settings)
    # No capable worker at all -> dispatch escalates immediately.
    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=contractor_headers)
    wr = create_res.json()
    dispatch_res = client.post(f"{WORK_REQS}/{wr['id']}/dispatch", headers=contractor_headers)
    (position,) = dispatch_res.json()["positions"]
    assert position["status"] == "ESCALATED"

    res = client.post(f"{POSITIONS}/{position['positionId']}/execution", headers=contractor_headers)
    assert res.status_code == 409, res.text


def test_cancelled_position_cannot_create_execution(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    _, contractor_headers = _contractor_auth(db_session, test_settings)
    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=contractor_headers)
    wr = create_res.json()

    # CANCELLED is reachable in the state machine but no route in this
    # codebase ever produces it (see docs/Dispatch.md) — manufacture it
    # directly via the ORM, same convention test_dispatch.py already uses
    # for scenarios no route can naturally construct.
    row = db_session.query(DispatchPositionModel).filter_by(work_requirement_id=wr["id"]).one()
    row.status = PositionStatus.CANCELLED.value
    db_session.commit()

    res = client.post(f"{POSITIONS}/{row.id}/execution", headers=contractor_headers)
    assert res.status_code == 409, res.text


# ---------------------------------------------------------------------------
# 6. Repeated creation is idempotent.
# ---------------------------------------------------------------------------
def test_repeated_creation_is_idempotent(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    _, position_id, _, contractor_headers, _ = _committed_position(client, db_session, test_settings)

    first = _create_execution(client, contractor_headers, position_id)
    assert first.status_code == 201
    second = _create_execution(client, contractor_headers, position_id)
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]

    count = db_session.query(ShiftModel).filter_by(dispatch_position_id=position_id).count()
    assert count == 1


# ---------------------------------------------------------------------------
# 7. Database prevents two executions for one DispatchPosition.
# ---------------------------------------------------------------------------
def test_database_prevents_duplicate_execution(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    _, position_id, worker, contractor_headers, _ = _committed_position(client, db_session, test_settings)
    _create_execution(client, contractor_headers, position_id)

    duplicate = ShiftModel(dispatch_position_id=position_id, worker_id=worker.worker.id, status="SCHEDULED")
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ---------------------------------------------------------------------------
# 8. Correct committed worker owns execution.
# ---------------------------------------------------------------------------
def test_execution_worker_matches_committed_worker(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    _, position_id, worker, contractor_headers, _ = _committed_position(client, db_session, test_settings)
    res = _create_execution(client, contractor_headers, position_id)
    assert res.json()["workerId"] == worker.worker.id


# ---------------------------------------------------------------------------
# 9. Worker can retrieve own execution.
# ---------------------------------------------------------------------------
def test_worker_can_retrieve_own_execution(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    wr_id, position_id, worker, contractor_headers, worker_headers = _committed_position(
        client, db_session, test_settings
    )
    created = _create_execution(client, contractor_headers, position_id).json()

    res = client.get(f"{EXECUTIONS}/{created['id']}", headers=worker_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["id"] == created["id"]
    assert body["workRequirementId"] == wr_id
    assert body["workerId"] == worker.worker.id


# ---------------------------------------------------------------------------
# 10. Worker cannot mutate another worker's execution.
# ---------------------------------------------------------------------------
def test_worker_cannot_mutate_another_workers_execution(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    _, position_id, _, contractor_headers, _ = _committed_position(client, db_session, test_settings)
    created = _create_execution(client, contractor_headers, position_id).json()

    other_worker = create_worker(db_session, city="Bengaluru")
    other_headers = _worker_auth(other_worker, test_settings)

    assert client.get(f"{EXECUTIONS}/{created['id']}", headers=other_headers).status_code == 403
    assert (
        client.post(f"{EXECUTIONS}/{created['id']}/check-in", headers=other_headers).status_code == 403
    )
    assert client.post(f"{EXECUTIONS}/{created['id']}/start", headers=other_headers).status_code == 403
    assert (
        client.post(f"{EXECUTIONS}/{created['id']}/complete", headers=other_headers).status_code == 403
    )


# ---------------------------------------------------------------------------
# 11-12. SCHEDULED -> CHECKED_IN, check-in timestamp recorded.
# ---------------------------------------------------------------------------
def test_check_in_transitions_and_records_timestamp(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    _, position_id, _, contractor_headers, worker_headers = _committed_position(
        client, db_session, test_settings
    )
    created = _create_execution(client, contractor_headers, position_id).json()

    res = client.post(f"{EXECUTIONS}/{created['id']}/check-in", headers=worker_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "CHECKED_IN"
    assert body["checkInAt"] is not None


# ---------------------------------------------------------------------------
# 13. CHECKED_IN -> WORKING.
# ---------------------------------------------------------------------------
def test_start_transitions_to_working(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    _, position_id, _, contractor_headers, worker_headers = _committed_position(
        client, db_session, test_settings
    )
    created = _create_execution(client, contractor_headers, position_id).json()
    client.post(f"{EXECUTIONS}/{created['id']}/check-in", headers=worker_headers)

    res = client.post(f"{EXECUTIONS}/{created['id']}/start", headers=worker_headers)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "WORKING"


# ---------------------------------------------------------------------------
# 14-15. WORKING -> COMPLETED, completion timestamp recorded.
# ---------------------------------------------------------------------------
def test_complete_transitions_and_records_timestamp(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    _, position_id, _, contractor_headers, worker_headers = _committed_position(
        client, db_session, test_settings
    )
    created = _create_execution(client, contractor_headers, position_id).json()
    client.post(f"{EXECUTIONS}/{created['id']}/check-in", headers=worker_headers)
    client.post(f"{EXECUTIONS}/{created['id']}/start", headers=worker_headers)

    res = client.post(f"{EXECUTIONS}/{created['id']}/complete", headers=worker_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "COMPLETED"
    assert body["completedAt"] is not None


# ---------------------------------------------------------------------------
# 16. Cannot check in twice.
# ---------------------------------------------------------------------------
def test_cannot_check_in_twice(client: TestClient, db_session: Session, test_settings: Settings) -> None:
    _, position_id, _, contractor_headers, worker_headers = _committed_position(
        client, db_session, test_settings
    )
    created = _create_execution(client, contractor_headers, position_id).json()
    client.post(f"{EXECUTIONS}/{created['id']}/check-in", headers=worker_headers)

    res = client.post(f"{EXECUTIONS}/{created['id']}/check-in", headers=worker_headers)
    assert res.status_code == 409


# ---------------------------------------------------------------------------
# 17. Cannot complete before check-in.
# ---------------------------------------------------------------------------
def test_cannot_complete_before_check_in(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    _, position_id, _, contractor_headers, worker_headers = _committed_position(
        client, db_session, test_settings
    )
    created = _create_execution(client, contractor_headers, position_id).json()

    res = client.post(f"{EXECUTIONS}/{created['id']}/complete", headers=worker_headers)
    assert res.status_code == 409


# ---------------------------------------------------------------------------
# 18. Cannot complete twice.
# ---------------------------------------------------------------------------
def test_cannot_complete_twice(client: TestClient, db_session: Session, test_settings: Settings) -> None:
    _, position_id, _, contractor_headers, worker_headers = _committed_position(
        client, db_session, test_settings
    )
    created = _create_execution(client, contractor_headers, position_id).json()
    client.post(f"{EXECUTIONS}/{created['id']}/check-in", headers=worker_headers)
    client.post(f"{EXECUTIONS}/{created['id']}/start", headers=worker_headers)
    first = client.post(f"{EXECUTIONS}/{created['id']}/complete", headers=worker_headers)
    assert first.status_code == 200

    second = client.post(f"{EXECUTIONS}/{created['id']}/complete", headers=worker_headers)
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# 19. Cannot start after completion.
# ---------------------------------------------------------------------------
def test_cannot_start_after_completion(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    _, position_id, _, contractor_headers, worker_headers = _committed_position(
        client, db_session, test_settings
    )
    created = _create_execution(client, contractor_headers, position_id).json()
    client.post(f"{EXECUTIONS}/{created['id']}/check-in", headers=worker_headers)
    client.post(f"{EXECUTIONS}/{created['id']}/start", headers=worker_headers)
    client.post(f"{EXECUTIONS}/{created['id']}/complete", headers=worker_headers)

    res = client.post(f"{EXECUTIONS}/{created['id']}/start", headers=worker_headers)
    assert res.status_code == 409


# ---------------------------------------------------------------------------
# Supporting authorization test: creation is contractor-owner/admin only.
# ---------------------------------------------------------------------------
def test_create_execution_forbidden_for_non_owning_contractor(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    _, position_id, _, _, _ = _committed_position(client, db_session, test_settings)
    _, other_headers = _contractor_auth(db_session, test_settings)

    res = client.post(f"{POSITIONS}/{position_id}/execution", headers=other_headers)
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# MOST IMPORTANT INTEGRATION TEST: full flow from WorkRequirement creation
# through completion, verifying final state and timestamps.
# ---------------------------------------------------------------------------
def test_end_to_end_work_requirement_to_completed_execution(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)

    mason = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=mason.worker.id, task_id=task.id, level=3)

    # WorkRequirement -> CrewRequirement
    create_res = client.post(
        WORK_REQS,
        json={
            "city": "Bengaluru",
            "state": "Karnataka",
            "requestedFor": "2026-10-05T09:00:00Z",
            "lines": [{"taskId": task.id, "minLevel": 3, "quantity": 1}],
        },
        headers=contractor_headers,
    )
    assert create_res.status_code == 201
    wr = create_res.json()

    # Dispatch -> DispatchOffer PENDING
    dispatch_res = client.post(f"{WORK_REQS}/{wr['id']}/dispatch", headers=contractor_headers)
    assert dispatch_res.status_code == 200
    (position,) = dispatch_res.json()["positions"]
    offer = position["offer"]
    assert offer["workerId"] == mason.worker.id

    # Worker accepts -> DispatchPosition COMMITTED
    mason_headers = _worker_auth(mason, test_settings)
    accept_res = client.post(f"{OFFERS}/{offer['id']}/accept", headers=mason_headers)
    assert accept_res.status_code == 200
    assert accept_res.json()["workRequirementDispatchStatus"] == "FULFILLED"

    # Create execution
    exec_res = client.post(f"{POSITIONS}/{position['positionId']}/execution", headers=contractor_headers)
    assert exec_res.status_code == 201, exec_res.text
    execution = exec_res.json()
    assert execution["dispatchPositionId"] == position["positionId"]
    assert execution["workerId"] == mason.worker.id
    assert execution["workRequirementId"] == wr["id"]
    assert execution["crewRequirementId"] == wr["lines"][0]["id"]
    assert execution["scheduledFor"] is not None
    assert execution["status"] == "SCHEDULED"

    # Check-in
    check_in_res = client.post(f"{EXECUTIONS}/{execution['id']}/check-in", headers=mason_headers)
    assert check_in_res.status_code == 200
    assert check_in_res.json()["status"] == "CHECKED_IN"
    assert check_in_res.json()["checkInAt"] is not None

    # Start
    start_res = client.post(f"{EXECUTIONS}/{execution['id']}/start", headers=mason_headers)
    assert start_res.status_code == 200
    assert start_res.json()["status"] == "WORKING"

    # Complete
    complete_res = client.post(f"{EXECUTIONS}/{execution['id']}/complete", headers=mason_headers)
    assert complete_res.status_code == 200
    final = complete_res.json()
    assert final["status"] == "COMPLETED"
    assert final["checkInAt"] is not None
    assert final["completedAt"] is not None

    # Final state is stable and correctly attributed end-to-end.
    get_res = client.get(f"{EXECUTIONS}/{execution['id']}", headers=mason_headers)
    assert get_res.status_code == 200
    assert get_res.json() == final
