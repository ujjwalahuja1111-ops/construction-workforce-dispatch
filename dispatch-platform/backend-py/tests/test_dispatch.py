"""
End-to-end product tests for "DISPATCH + COMMITMENT" — the vertical slice
that turns Phase F's dispatch *candidates* into actual dispatch *positions*,
*offers*, and worker *commitment*:

    ELIGIBLE WORKERS -> DISPATCH OFFER -> WORKER ACCEPTS -> COMMITTED
        -> another position dispatched -> all positions COMMITTED
        -> crew FULFILLED (by actual commitment, not candidate assembly)

Every request goes through the real FastAPI app (`client` fixture), same
discipline as test_work_requirements.py. Covers all 10 mandated test
scenarios verbatim (search each docstring for "TEST N"), plus the
authorization/invalid-transition behaviour those scenarios depend on.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.enums import PositionStatus
from app.infrastructure.db.models import DispatchOfferModel, TaskModel
from app.repositories.sqlalchemy_repositories import SqlAlchemyDispatchPositionRepository
from tests.factories import (
    CreatedWorker,
    auth_header,
    create_contractor,
    create_worker,
    grant_capability,
    grant_safety_qualification,
    seed_taxonomy,
)

WORK_REQS = "/api/work-requirements"
OFFERS = "/api/dispatch/offers"


def _contractor_auth(db: Session, settings: Settings) -> tuple[str, dict[str, str]]:
    contractor = create_contractor(db)
    headers = auth_header(
        user_id=contractor.user.id, role="CONTRACTOR", phone=contractor.user.phone, settings=settings
    )
    return contractor.user.id, headers


def _worker_auth(worker: CreatedWorker, settings: Settings) -> dict[str, str]:
    return auth_header(
        user_id=worker.user.id, role="WORKER", phone=worker.user.phone, settings=settings
    )


def _mason_request(
    tasks: dict[str, TaskModel],
    *,
    mason_qty: int = 1,
    helper_qty: int = 0,
    requested_for: str | None = None,
    safety_required: bool | None = None,
) -> dict[str, object]:
    brickwork_id = tasks["BRICKWORK_NEW_WALL"].id
    lines: list[dict[str, object]] = [{"taskId": brickwork_id, "minLevel": 3, "quantity": mason_qty}]
    if helper_qty:
        lines.append({"taskId": brickwork_id, "minLevel": 1, "quantity": helper_qty})
    if safety_required is not None:
        lines[0]["safetyQualificationRequired"] = safety_required
    payload: dict[str, object] = {"city": "Bengaluru", "state": "Karnataka", "lines": lines}
    if requested_for is not None:
        payload["requestedFor"] = requested_for
    return payload


def _dispatch(client: TestClient, headers: dict[str, str], work_requirement_id: str) -> Any:
    res = client.post(f"{WORK_REQS}/{work_requirement_id}/dispatch", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------------------
# TEST 1 — single position: 1 Mason L3+, dispatch, pending offer, accept,
# position COMMITTED, offer ACCEPTED, requirement FULFILLED.
# ---------------------------------------------------------------------------
def test_1_single_position_dispatch_accept_fulfils(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)

    mason = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=mason.worker.id, task_id=task.id, level=3)

    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=contractor_headers)
    assert create_res.status_code == 201
    wr = create_res.json()
    assert wr["dispatchStatus"] == "PARTIALLY_FULFILLED"  # not yet dispatched — unresolved, not a failure

    summary = _dispatch(client, contractor_headers, wr["id"])
    assert summary["requiredPositions"] == 1
    (position,) = summary["positions"]
    assert position["status"] == "OFFERED"
    offer = position["offer"]
    assert offer is not None
    assert offer["workerId"] == mason.worker.id
    assert offer["status"] == "PENDING"

    mason_headers = _worker_auth(mason, test_settings)
    accept_res = client.post(f"{OFFERS}/{offer['id']}/accept", headers=mason_headers)
    assert accept_res.status_code == 200, accept_res.text
    assignment = accept_res.json()
    assert assignment["workerId"] == mason.worker.id
    assert assignment["workRequirementDispatchStatus"] == "FULFILLED"

    get_res = client.get(f"{WORK_REQS}/{wr['id']}", headers=contractor_headers)
    body = get_res.json()
    assert body["dispatchStatus"] == "FULFILLED"
    assert body["committedPositions"] == 1
    assert body["lines"][0]["dispatchStatus"] == "FULFILLED"


# ---------------------------------------------------------------------------
# TEST 2 — real crew: 1 Mason L3+ + 2 Helper L1+, independent positions,
# accept all, no duplicate worker commitment, requirement FULFILLED.
# ---------------------------------------------------------------------------
def test_2_real_crew_independent_positions_no_double_booking(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)

    mason = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=mason.worker.id, task_id=task.id, level=3)
    helper_a = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=helper_a.worker.id, task_id=task.id, level=1)
    helper_b = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=helper_b.worker.id, task_id=task.id, level=1)

    create_res = client.post(
        WORK_REQS, json=_mason_request(tasks, helper_qty=2), headers=contractor_headers
    )
    wr = create_res.json()
    assert wr["requiredPositions"] == 3

    summary = _dispatch(client, contractor_headers, wr["id"])
    offered_workers = {p["offer"]["workerId"] for p in summary["positions"]}
    # The mason (level 3) also clears the helper line's level-1+ bar, but
    # assemble_crew's cross-line dedup means the mason is only ever offered
    # the mason position — three independent positions, three distinct
    # workers offered, never the same worker twice.
    assert offered_workers == {mason.worker.id, helper_a.worker.id, helper_b.worker.id}

    for position in summary["positions"]:
        offer = position["offer"]
        headers = _worker_auth(
            {mason.worker.id: mason, helper_a.worker.id: helper_a, helper_b.worker.id: helper_b}[
                offer["workerId"]
            ],
            test_settings,
        )
        res = client.post(f"{OFFERS}/{offer['id']}/accept", headers=headers)
        assert res.status_code == 200, res.text

    get_res = client.get(f"{WORK_REQS}/{wr['id']}", headers=contractor_headers)
    body = get_res.json()
    assert body["dispatchStatus"] == "FULFILLED"
    assert body["committedPositions"] == 3
    # Committed worker identity isn't in the read view (deliberately thin —
    # see EligibleWorkerOut) so we assert via distinct acceptance above and
    # via position/offer counts here.
    assert body["openPositions"] == 0
    assert body["escalatedPositions"] == 0


# ---------------------------------------------------------------------------
# TEST 3 — decline -> redispatch: A declines, position reopens, redispatch
# offers B, B accepts, B committed.
# ---------------------------------------------------------------------------
def test_3_decline_then_redispatch_offers_replacement(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)

    worker_a = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=worker_a.worker.id, task_id=task.id, level=3)
    worker_b = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=worker_b.worker.id, task_id=task.id, level=3)

    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=contractor_headers)
    wr = create_res.json()

    summary = _dispatch(client, contractor_headers, wr["id"])
    (position,) = summary["positions"]
    first_offer = position["offer"]
    assert first_offer["workerId"] == worker_a.worker.id

    a_headers = _worker_auth(worker_a, test_settings)
    decline_res = client.post(f"{OFFERS}/{first_offer['id']}/decline", headers=a_headers)
    assert decline_res.status_code == 200
    assert decline_res.json()["positionStatus"] == "OPEN"

    summary2 = _dispatch(client, contractor_headers, wr["id"])
    (position2,) = summary2["positions"]
    second_offer = position2["offer"]
    assert second_offer is not None
    assert second_offer["workerId"] == worker_b.worker.id  # A never re-offered for this position

    b_headers = _worker_auth(worker_b, test_settings)
    accept_res = client.post(f"{OFFERS}/{second_offer['id']}/accept", headers=b_headers)
    assert accept_res.status_code == 200
    assert accept_res.json()["workerId"] == worker_b.worker.id


# ---------------------------------------------------------------------------
# TEST 4 — expiry -> redispatch: same behaviour as decline, system-driven.
# ---------------------------------------------------------------------------
def test_4_expiry_then_redispatch_offers_another_candidate(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    contractor_id, contractor_headers = _contractor_auth(db_session, test_settings)

    worker_a = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=worker_a.worker.id, task_id=task.id, level=3)
    worker_b = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=worker_b.worker.id, task_id=task.id, level=3)

    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=contractor_headers)
    wr = create_res.json()

    summary = _dispatch(client, contractor_headers, wr["id"])
    (position,) = summary["positions"]
    offer = position["offer"]
    assert offer["workerId"] == worker_a.worker.id

    # Simulate a short-lived test offer: force this offer's expires_at into
    # the past directly (deterministic, no sleeping in a test suite).
    row = db_session.get(DispatchOfferModel, offer["id"])
    assert row is not None
    # Naive UTC — matches what SQLite (and thus every expires_at column
    # this app reads back) actually returns; see dispatch_service._utc_now.
    row.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
    db_session.commit()

    admin_headers = auth_header(
        user_id="admin-1", role="ADMIN", phone="+919800000000", settings=test_settings
    )
    expire_res = client.post(f"{OFFERS}/expire", headers=admin_headers)
    assert expire_res.status_code == 200
    processed = expire_res.json()["processed"]
    assert len(processed) == 1
    assert processed[0]["offerStatus"] == "EXPIRED"
    assert processed[0]["positionStatus"] == "OPEN"

    summary2 = _dispatch(client, contractor_headers, wr["id"])
    (position2,) = summary2["positions"]
    second_offer = position2["offer"]
    assert second_offer is not None
    assert second_offer["workerId"] == worker_b.worker.id


# ---------------------------------------------------------------------------
# TEST 5 — capability gate: a below-minimum worker must never receive an
# offer.
# ---------------------------------------------------------------------------
def test_5_capability_gate_excludes_below_minimum_worker(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)

    weak_worker = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=weak_worker.worker.id, task_id=task.id, level=2)

    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=contractor_headers)
    wr = create_res.json()

    summary = _dispatch(client, contractor_headers, wr["id"])
    (position,) = summary["positions"]
    assert position["offer"] is None
    assert position["status"] == "ESCALATED"


# ---------------------------------------------------------------------------
# TEST 6 — safety gate: a worker without the required safety qualification
# must never receive an offer.
# ---------------------------------------------------------------------------
def test_6_safety_gate_excludes_unqualified_worker(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)

    unqualified = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=unqualified.worker.id, task_id=task.id, level=3)
    qualified = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=qualified.worker.id, task_id=task.id, level=3)
    grant_safety_qualification(db_session, worker_id=qualified.worker.id, task_id=task.id)

    payload = _mason_request(tasks, safety_required=True)
    create_res = client.post(WORK_REQS, json=payload, headers=contractor_headers)
    wr = create_res.json()

    summary = _dispatch(client, contractor_headers, wr["id"])
    (position,) = summary["positions"]
    assert position["offer"]["workerId"] == qualified.worker.id


# ---------------------------------------------------------------------------
# TEST 7 — cross-work-requirement conflict: a worker committed to
# Requirement A must not be offered a conflicting position on Requirement B
# (same requested_for date).
# ---------------------------------------------------------------------------
def test_7_cross_work_requirement_conflict_excludes_committed_worker(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)

    only_worker = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=only_worker.worker.id, task_id=task.id, level=3)

    same_date = "2026-10-01T09:00:00Z"
    req_a = client.post(
        WORK_REQS, json=_mason_request(tasks, requested_for=same_date), headers=contractor_headers
    ).json()
    req_b = client.post(
        WORK_REQS, json=_mason_request(tasks, requested_for=same_date), headers=contractor_headers
    ).json()

    summary_a = _dispatch(client, contractor_headers, req_a["id"])
    offer_a = summary_a["positions"][0]["offer"]
    assert offer_a["workerId"] == only_worker.worker.id
    worker_headers = _worker_auth(only_worker, test_settings)
    accept_res = client.post(f"{OFFERS}/{offer_a['id']}/accept", headers=worker_headers)
    assert accept_res.status_code == 200

    summary_b = _dispatch(client, contractor_headers, req_b["id"])
    position_b = summary_b["positions"][0]
    # The only capable worker is already committed to a conflicting
    # (same-date) requirement — no valid candidate remains.
    assert position_b["offer"] is None
    assert position_b["status"] == "ESCALATED"


# ---------------------------------------------------------------------------
# TEST 8 — double-accept race: two concurrent acceptance attempts for one
# position; exactly one succeeds, exactly one worker committed.
#
# The test harness's in-memory SQLite database is a single, non-thread-safe
# SQLAlchemy Session shared by every request (see conftest.py) — racing real
# threads against it would test the harness's thread-safety, not the
# application's, and could fail with unrelated session-reentrancy errors
# rather than the 409 this scenario is actually about. So this test drives
# the exact mechanism that guarantees "exactly one succeeds" directly: the
# atomic `UPDATE ... WHERE status = :expected` guard
# (SqlAlchemyDispatchPositionRepository.try_transition) is what makes the
# race safe under genuine concurrent connections (e.g. Postgres in
# production) — a single SQL statement either matches the row or it
# doesn't, with no window for two callers to both "win". This test proves
# that guard actually rejects a stale-state write: accept worker A normally
# (through the real HTTP endpoint), then attempt the SAME position
# transition a second time with the pre-acceptance expected status — the
# call a concurrent second request would have made had it read the
# position before A's commit landed — and assert it is refused.
# ---------------------------------------------------------------------------
def test_8_concurrent_accept_race_exactly_one_wins(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)

    worker_a = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=worker_a.worker.id, task_id=task.id, level=3)
    worker_b = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=worker_b.worker.id, task_id=task.id, level=3)

    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=contractor_headers)
    wr = create_res.json()
    summary = _dispatch(client, contractor_headers, wr["id"])
    position_id = summary["positions"][0]["positionId"]
    offer_a = summary["positions"][0]["offer"]
    assert offer_a["workerId"] == worker_a.worker.id

    a_headers = _worker_auth(worker_a, test_settings)
    accept_res = client.post(f"{OFFERS}/{offer_a['id']}/accept", headers=a_headers)
    assert accept_res.status_code == 200
    assert accept_res.json()["workerId"] == worker_a.worker.id

    # Simulate the second, concurrent request: it would have read the
    # position while still OFFERED (before A's write landed) and then
    # attempted to commit worker B onto it. The guarded UPDATE must find
    # zero matching rows — the position is no longer OFFERED — and refuse.
    positions_repo = SqlAlchemyDispatchPositionRepository(db_session)
    applied = positions_repo.try_transition(
        position_id,
        expected_status=PositionStatus.OFFERED,
        new_status=PositionStatus.COMMITTED,
        worker_id=worker_b.worker.id,
    )
    assert applied is False

    get_res = client.get(f"{WORK_REQS}/{wr['id']}", headers=contractor_headers)
    body = get_res.json()
    assert body["committedPositions"] == 1  # exactly one worker committed, never two


# ---------------------------------------------------------------------------
# TEST 9 — competing offers: two workers have offers for one position; one
# accepts; the other offer becomes CANCELLED.
# ---------------------------------------------------------------------------
def test_9_competing_offer_is_cancelled_on_acceptance(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)

    worker_a = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=worker_a.worker.id, task_id=task.id, level=3)
    worker_b = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=worker_b.worker.id, task_id=task.id, level=3)

    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=contractor_headers)
    wr = create_res.json()
    summary = _dispatch(client, contractor_headers, wr["id"])
    position_id = summary["positions"][0]["positionId"]
    offer_a = summary["positions"][0]["offer"]

    # Manufacture a second, competing PENDING offer for the same position
    # (the normal dispatch loop would never create two live offers for one
    # position — this is the scenario the order asks us to prove is safe
    # regardless of how it arises).
    competing = DispatchOfferModel(
        position_id=position_id,
        worker_id=worker_b.worker.id,
        status="PENDING",
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=15),
    )
    db_session.add(competing)
    db_session.commit()
    db_session.refresh(competing)

    a_headers = _worker_auth(worker_a, test_settings)
    accept_res = client.post(f"{OFFERS}/{offer_a['id']}/accept", headers=a_headers)
    assert accept_res.status_code == 200

    row = db_session.get(DispatchOfferModel, competing.id)
    assert row is not None
    db_session.refresh(row)
    assert row.status == "CANCELLED"


# ---------------------------------------------------------------------------
# TEST 10 — exhaustion: all valid candidates decline/expire; explicit
# escalation, no silent failure.
# ---------------------------------------------------------------------------
def test_10_exhaustion_escalates_explicitly(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)

    only_worker = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=only_worker.worker.id, task_id=task.id, level=3)

    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=contractor_headers)
    wr = create_res.json()
    summary = _dispatch(client, contractor_headers, wr["id"])
    offer = summary["positions"][0]["offer"]
    assert offer["workerId"] == only_worker.worker.id

    worker_headers = _worker_auth(only_worker, test_settings)
    decline_res = client.post(f"{OFFERS}/{offer['id']}/decline", headers=worker_headers)
    assert decline_res.status_code == 200

    # Redispatch: the only candidate already declined for THIS position, so
    # no valid candidate remains -> explicit ESCALATED, never silent OPEN.
    summary2 = _dispatch(client, contractor_headers, wr["id"])
    position2 = summary2["positions"][0]
    assert position2["offer"] is None
    assert position2["status"] == "ESCALATED"

    get_res = client.get(f"{WORK_REQS}/{wr['id']}", headers=contractor_headers)
    body = get_res.json()
    assert body["dispatchStatus"] == "ESCALATED"
    assert body["escalatedPositions"] == 1


# ---------------------------------------------------------------------------
# Supporting authorization / invalid-transition tests.
# ---------------------------------------------------------------------------
def test_dispatch_forbidden_for_non_owning_contractor(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    _, owner_headers = _contractor_auth(db_session, test_settings)
    _, other_headers = _contractor_auth(db_session, test_settings)

    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=owner_headers)
    wr = create_res.json()

    res = client.post(f"{WORK_REQS}/{wr['id']}/dispatch", headers=other_headers)
    assert res.status_code == 403


def test_accept_forbidden_for_non_owning_worker(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)

    mason = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=mason.worker.id, task_id=task.id, level=3)
    other_worker = create_worker(db_session, city="Bengaluru")

    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=contractor_headers)
    wr = create_res.json()
    summary = _dispatch(client, contractor_headers, wr["id"])
    offer = summary["positions"][0]["offer"]

    other_headers = _worker_auth(other_worker, test_settings)
    res = client.post(f"{OFFERS}/{offer['id']}/accept", headers=other_headers)
    assert res.status_code == 403


def test_double_accept_same_offer_is_rejected(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)

    mason = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=mason.worker.id, task_id=task.id, level=3)

    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=contractor_headers)
    wr = create_res.json()
    summary = _dispatch(client, contractor_headers, wr["id"])
    offer = summary["positions"][0]["offer"]

    mason_headers = _worker_auth(mason, test_settings)
    first = client.post(f"{OFFERS}/{offer['id']}/accept", headers=mason_headers)
    assert first.status_code == 200
    second = client.post(f"{OFFERS}/{offer['id']}/accept", headers=mason_headers)
    assert second.status_code == 409


def test_worker_can_list_own_pending_offer(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    """GET /api/dispatch/offers — the worker-owned offer-visibility
    endpoint added for the product-test sprint (see docs/Dispatch.md)."""
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)

    mason = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=mason.worker.id, task_id=task.id, level=3)

    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=contractor_headers)
    wr = create_res.json()
    summary = _dispatch(client, contractor_headers, wr["id"])
    offer = summary["positions"][0]["offer"]

    mason_headers = _worker_auth(mason, test_settings)
    res = client.get(OFFERS, headers=mason_headers)
    assert res.status_code == 200, res.text
    offers = res.json()
    assert len(offers) == 1
    assert offers[0]["id"] == offer["id"]
    assert offers[0]["status"] == "PENDING"
    assert offers[0]["workRequirementId"] == wr["id"]
    assert offers[0]["taskCode"] == "BRICKWORK_NEW_WALL"
    assert offers[0]["minLevel"] == 3


def test_worker_sees_only_own_offers_never_anothers(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)

    mason = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=mason.worker.id, task_id=task.id, level=3)
    bystander = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=bystander.worker.id, task_id=task.id, level=3)

    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=contractor_headers)
    wr = create_res.json()
    _dispatch(client, contractor_headers, wr["id"])

    # The bystander was never offered this position (mason won the
    # deterministic ordering) and has no offers of their own.
    bystander_headers = _worker_auth(bystander, test_settings)
    res = client.get(OFFERS, headers=bystander_headers)
    assert res.status_code == 200
    assert res.json() == []


def test_offer_list_reflects_accepted_status_after_acceptance(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)

    mason = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=mason.worker.id, task_id=task.id, level=3)

    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=contractor_headers)
    wr = create_res.json()
    summary = _dispatch(client, contractor_headers, wr["id"])
    offer = summary["positions"][0]["offer"]

    mason_headers = _worker_auth(mason, test_settings)
    client.post(f"{OFFERS}/{offer['id']}/accept", headers=mason_headers)

    res = client.get(OFFERS, headers=mason_headers)
    assert res.json()[0]["status"] == "ACCEPTED"


def test_list_offers_forbidden_without_worker_profile(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    _, contractor_headers = _contractor_auth(db_session, test_settings)
    res = client.get(OFFERS, headers=contractor_headers)
    assert res.status_code == 403


def test_decline_of_already_accepted_offer_is_rejected(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, contractor_headers = _contractor_auth(db_session, test_settings)

    mason = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=mason.worker.id, task_id=task.id, level=3)

    create_res = client.post(WORK_REQS, json=_mason_request(tasks), headers=contractor_headers)
    wr = create_res.json()
    summary = _dispatch(client, contractor_headers, wr["id"])
    offer = summary["positions"][0]["offer"]

    mason_headers = _worker_auth(mason, test_settings)
    accept_res = client.post(f"{OFFERS}/{offer['id']}/accept", headers=mason_headers)
    assert accept_res.status_code == 200

    decline_res = client.post(f"{OFFERS}/{offer['id']}/decline", headers=mason_headers)
    assert decline_res.status_code == 409
