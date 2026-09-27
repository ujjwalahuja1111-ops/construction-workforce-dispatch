"""
PRODUCT TEST SPRINT — the one explicit integration test covering the
complete core product journey end-to-end, through the real HTTP/API
boundary (the `client` fixture's FastAPI TestClient), not a unit-test
simulation of internal service methods:

    CONTRACTOR authenticates
        -> creates WorkRequirement (classified into a CrewRequirement)
        -> dispatches -> WORKER receives a DispatchOffer
    WORKER authenticates
        -> discovers the offer via GET /api/dispatch/offers
        -> accepts it -> DispatchPosition becomes COMMITTED
    CONTRACTOR creates an execution for the committed position
    WORKER retrieves it, checks in, starts, completes
        -> Execution reaches COMPLETED

At every important transition this test queries the persisted ORM rows
directly (not just the HTTP response body) to verify the database actually
ended up in the state the API claims it did.

"Authenticates" here means obtaining a valid bearer token through the
existing JWT mechanism (`create_access_token`) — the same mechanism
`tests/factories.py:auth_header` already uses for every other test in this
suite, and the same one `scripts/dev_seed.py` uses for a live server.
backend-py has no phone+OTP HTTP login endpoint of its own yet (see
docs/PythonMigration.md); this is not a shortcut invented for this test.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.infrastructure.db.models import (
    CrewRequirementModel,
    DispatchOfferModel,
    DispatchPositionModel,
    ShiftModel,
    WorkRequirementModel,
)
from tests.factories import auth_header, create_contractor, create_worker, grant_capability, seed_taxonomy

WORK_REQS = "/api/work-requirements"
OFFERS = "/api/dispatch/offers"
POSITIONS = "/api/dispatch-positions"
EXECUTIONS = "/api/executions"


def test_complete_product_journey_contractor_to_completed_execution(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    # ---- Fixtures: taxonomy + one capable worker (existing test infra) ----
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]

    contractor = create_contractor(db_session)
    worker = create_worker(db_session, city="Bengaluru", state="Karnataka")
    grant_capability(db_session, worker_id=worker.worker.id, task_id=task.id, level=3)

    # ---- 1. Contractor authenticates ----
    contractor_headers = auth_header(
        user_id=contractor.user.id, role="CONTRACTOR", phone=contractor.user.phone, settings=test_settings
    )

    # ---- 2-4. Create WorkRequirement -> classified -> CrewRequirement ----
    create_res = client.post(
        WORK_REQS,
        json={
            "city": "Bengaluru",
            "state": "Karnataka",
            "requestedFor": "2026-10-12T09:00:00Z",
            "lines": [{"taskId": task.id, "minLevel": 3, "quantity": 1}],
        },
        headers=contractor_headers,
    )
    assert create_res.status_code == 201, create_res.text
    wr = create_res.json()

    wr_row = db_session.get(WorkRequirementModel, wr["id"])
    assert wr_row is not None
    crew_row = db_session.query(CrewRequirementModel).filter_by(work_requirement_id=wr["id"]).one()
    assert crew_row.task_id == task.id
    assert crew_row.min_level == 3

    # ---- 5. Eligible worker exists (asserted via the create response) ----
    assert wr["lines"][0]["eligibleCount"] == 1

    # ---- 6. Contractor dispatches -> Worker receives a DispatchOffer ----
    dispatch_res = client.post(f"{WORK_REQS}/{wr['id']}/dispatch", headers=contractor_headers)
    assert dispatch_res.status_code == 200, dispatch_res.text
    (position_outcome,) = dispatch_res.json()["positions"]
    assert position_outcome["status"] == "OFFERED"
    offer_id = position_outcome["offer"]["id"]
    position_id = position_outcome["positionId"]

    position_row = db_session.get(DispatchPositionModel, position_id)
    assert position_row is not None
    assert position_row.status == "OFFERED"
    offer_row = db_session.get(DispatchOfferModel, offer_id)
    assert offer_row is not None
    assert offer_row.status == "PENDING"
    assert offer_row.worker_id == worker.worker.id

    # ---- 7. Worker authenticates ----
    worker_headers = auth_header(
        user_id=worker.user.id, role="WORKER", phone=worker.user.phone, settings=test_settings
    )

    # ---- 8. Worker retrieves own pending offer ----
    my_offers_res = client.get(OFFERS, headers=worker_headers)
    assert my_offers_res.status_code == 200, my_offers_res.text
    my_offers = my_offers_res.json()
    assert len(my_offers) == 1
    assert my_offers[0]["id"] == offer_id
    assert my_offers[0]["status"] == "PENDING"
    assert my_offers[0]["positionId"] == position_id

    # ---- 9. Worker accepts the offer ----
    accept_res = client.post(f"{OFFERS}/{offer_id}/accept", headers=worker_headers)
    assert accept_res.status_code == 200, accept_res.text
    assert accept_res.json()["workerId"] == worker.worker.id

    # ---- 10. DispatchPosition becomes COMMITTED (persisted state) ----
    db_session.refresh(position_row)
    assert position_row.status == "COMMITTED"
    assert position_row.worker_id == worker.worker.id
    db_session.refresh(offer_row)
    assert offer_row.status == "ACCEPTED"

    # ---- 11. Contractor creates execution ----
    exec_res = client.post(f"{POSITIONS}/{position_id}/execution", headers=contractor_headers)
    assert exec_res.status_code == 201, exec_res.text
    execution = exec_res.json()
    assert execution["dispatchPositionId"] == position_id
    assert execution["workerId"] == worker.worker.id
    assert execution["status"] == "SCHEDULED"

    shift_row = db_session.get(ShiftModel, execution["id"])
    assert shift_row is not None
    assert shift_row.status == "SCHEDULED"
    assert shift_row.dispatch_position_id == position_id
    assert shift_row.worker_id == worker.worker.id

    # ---- 12. Worker retrieves/uses own execution ----
    get_exec_res = client.get(f"{EXECUTIONS}/{execution['id']}", headers=worker_headers)
    assert get_exec_res.status_code == 200
    assert get_exec_res.json()["id"] == execution["id"]

    # ---- 13. Worker checks in ----
    check_in_res = client.post(f"{EXECUTIONS}/{execution['id']}/check-in", headers=worker_headers)
    assert check_in_res.status_code == 200, check_in_res.text
    assert check_in_res.json()["status"] == "CHECKED_IN"
    db_session.refresh(shift_row)
    assert shift_row.status == "CHECKED_IN"
    assert shift_row.check_in_at is not None

    # ---- 14. Worker starts ----
    start_res = client.post(f"{EXECUTIONS}/{execution['id']}/start", headers=worker_headers)
    assert start_res.status_code == 200, start_res.text
    assert start_res.json()["status"] == "WORKING"
    db_session.refresh(shift_row)
    assert shift_row.status == "WORKING"

    # ---- 15. Worker completes ----
    complete_res = client.post(f"{EXECUTIONS}/{execution['id']}/complete", headers=worker_headers)
    assert complete_res.status_code == 200, complete_res.text
    final = complete_res.json()
    assert final["status"] == "COMPLETED"
    assert final["checkInAt"] is not None
    assert final["completedAt"] is not None

    # ---- 16. Execution reaches COMPLETED (final persisted state) ----
    db_session.refresh(shift_row)
    assert shift_row.status == "COMPLETED"
    assert shift_row.check_in_at is not None
    assert shift_row.completed_at is not None

    # Final cross-check: the whole chain ends exactly where the Definition
    # of Done says it must.
    db_session.refresh(position_row)
    db_session.refresh(offer_row)
    assert position_row.status == "COMMITTED"
    assert offer_row.status == "ACCEPTED"
    assert shift_row.status == "COMPLETED"
