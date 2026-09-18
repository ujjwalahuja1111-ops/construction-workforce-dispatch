"""
End-to-end product test for the CTO's Phase F pipeline:

    CLIENT WORK REQUEST -> CLASSIFIED REQUIREMENT -> CREW REQUIREMENT
        -> ELIGIBLE WORKERS -> CREW ASSEMBLY / DISPATCH CANDIDATES

Every request goes through the real FastAPI app (`client` fixture), not the
service layer directly — this exercises the real routing/auth/validation/
persistence/matching chain end to end, the same discipline
test_worker_capabilities.py already uses.

Covers the four scenarios the CTO's execution order requires verbatim
(search each docstring for "TEST SCENARIO"), plus the access-control and
input-validation behaviour those scenarios depend on being correct.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.infrastructure.db.models import TaskModel
from tests.factories import (
    auth_header,
    create_contractor,
    create_worker,
    grant_capability,
    grant_safety_qualification,
    seed_taxonomy,
    set_capability_level,
)

WORK_REQS = "/api/work-requirements"


def _contractor_auth(db: Session, settings: Settings) -> tuple[str, dict[str, str]]:
    contractor = create_contractor(db)
    headers = auth_header(
        user_id=contractor.user.id, role="CONTRACTOR", phone=contractor.user.phone, settings=settings
    )
    return contractor.user.id, headers


def _brickwork_request(
    tasks: dict[str, TaskModel], *, mason_qty: int = 1, helper_qty: int = 2
) -> dict[str, object]:
    brickwork_id = tasks["BRICKWORK_NEW_WALL"].id
    return {
        "city": "Bengaluru",
        "state": "Karnataka",
        "lines": [
            {"taskId": brickwork_id, "minLevel": 3, "quantity": mason_qty},
            {"taskId": brickwork_id, "minLevel": 1, "quantity": helper_qty},
        ],
    }


# ---------------------------------------------------------------------------
# TEST SCENARIO 1 — contractor requests 1 Mason L3+ / 2 Helper L1+; the
# system classifies, persists, finds eligible workers, and assembles the
# crew candidates.
# ---------------------------------------------------------------------------
def test_scenario_1_crew_request_is_classified_and_assembled(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    contractor_id, headers = _contractor_auth(db_session, test_settings)

    mason = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=mason.worker.id, task_id=task.id, level=3)
    helper_a = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=helper_a.worker.id, task_id=task.id, level=1)
    helper_b = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=helper_b.worker.id, task_id=task.id, level=1)

    res = client.post(WORK_REQS, json=_brickwork_request(tasks=tasks), headers=headers)
    assert res.status_code == 201
    body = res.json()

    assert body["contractorUserId"] == contractor_id
    assert body["status"] == "FULFILLED"
    assert len(body["lines"]) == 2

    mason_line, helper_line = body["lines"]
    assert mason_line["minLevel"] == 3
    assert mason_line["quantity"] == 1
    assert mason_line["status"] == "FULFILLED"
    assert mason_line["eligibleCount"] == 1
    assert [c["workerId"] for c in mason_line["candidates"]] == [mason.worker.id]

    assert helper_line["minLevel"] == 1
    assert helper_line["quantity"] == 2
    assert helper_line["status"] == "FULFILLED"
    # Eligibility is per-line and undeduplicated: the mason (level 3) also
    # clears the helper line's level-1+ bar, so all three workers show up
    # here. Candidate ASSEMBLY is what dedupes across lines (see
    # matching_service.assemble_crew) — the mason was already claimed by
    # the mason line, so only the two dedicated helpers are proposed below.
    assert helper_line["eligibleCount"] == 3
    assert {c["workerId"] for c in helper_line["candidates"]} == {helper_a.worker.id, helper_b.worker.id}

    # GET recomputes live and agrees with the POST response.
    get_res = client.get(f"{WORK_REQS}/{body['id']}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["status"] == "FULFILLED"


# ---------------------------------------------------------------------------
# TEST SCENARIO 2 — the exact required crew is not available; the system
# does not silently fail, it reports PARTIALLY_FULFILLED (some, not enough)
# and ESCALATED (none at all) as explicit states.
# ---------------------------------------------------------------------------
def test_scenario_2_unavailable_crew_escalates_instead_of_failing_silently(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BRICKWORK_NEW_WALL"]
    _, headers = _contractor_auth(db_session, test_settings)

    mason = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=mason.worker.id, task_id=task.id, level=3)
    only_one_helper = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=only_one_helper.worker.id, task_id=task.id, level=1)
    # helper_qty=2 requested, only 1 eligible helper exists.

    res = client.post(WORK_REQS, json=_brickwork_request(tasks=tasks), headers=headers)
    assert res.status_code == 201
    body = res.json()

    assert body["status"] == "PARTIALLY_FULFILLED"
    mason_line, helper_line = body["lines"]
    assert mason_line["status"] == "FULFILLED"
    assert helper_line["status"] == "PARTIALLY_FULFILLED"
    # Raw eligibility still includes the mason (level 3 clears level-1+),
    # but assembly already gave the mason to the mason line — status is
    # based on the one assembled candidate left, not this raw count of 2.
    assert helper_line["eligibleCount"] == 2
    assert len(helper_line["candidates"]) == 1

    # Now zero eligible helpers at all -> ESCALATED, not an empty 200 that
    # looks like success.
    res2 = client.post(
        WORK_REQS,
        json={
            "city": "Bengaluru",
            "state": "Karnataka",
            "lines": [{"taskId": tasks["FAULT_FINDING"].id, "minLevel": 2, "quantity": 1}],
        },
        headers=headers,
    )
    assert res2.status_code == 201
    body2 = res2.json()
    assert body2["status"] == "ESCALATED"
    assert body2["lines"][0]["status"] == "ESCALATED"
    assert body2["lines"][0]["eligibleCount"] == 0
    assert body2["lines"][0]["candidates"] == []


# ---------------------------------------------------------------------------
# TEST SCENARIO 3 — a worker who does not meet the minimum capability level
# is excluded from the eligible pool entirely.
# ---------------------------------------------------------------------------
def test_scenario_3_worker_below_minimum_level_is_excluded(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["WIRING"]
    _, headers = _contractor_auth(db_session, test_settings)

    underqualified = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=underqualified.worker.id, task_id=task.id, level=2)

    res = client.post(
        WORK_REQS,
        json={
            "city": "Bengaluru",
            "state": "Karnataka",
            "lines": [{"taskId": task.id, "minLevel": 3, "quantity": 1}],
        },
        headers=headers,
    )
    assert res.status_code == 201
    line = res.json()["lines"][0]
    assert line["status"] == "ESCALATED"
    assert line["eligibleCount"] == 0
    assert all(c["workerId"] != underqualified.worker.id for c in line["eligibleWorkers"])

    # Raise that worker to the minimum and confirm they now appear —
    # proves the exclusion above was really about the level, not a fluke.
    set_capability_level(db_session, worker_id=underqualified.worker.id, task_id=task.id, level=3)
    res2 = client.post(
        WORK_REQS,
        json={
            "city": "Bengaluru",
            "state": "Karnataka",
            "lines": [{"taskId": task.id, "minLevel": 3, "quantity": 1}],
        },
        headers=headers,
    )
    line2 = res2.json()["lines"][0]
    assert line2["status"] == "FULFILLED"
    assert line2["candidates"][0]["workerId"] == underqualified.worker.id


# ---------------------------------------------------------------------------
# TEST SCENARIO 4 — a safety-critical task requires the relevant
# qualification; an otherwise-matching worker without it is excluded.
# ---------------------------------------------------------------------------
def test_scenario_4_missing_safety_qualification_excludes_an_otherwise_matching_worker(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["WIRING"]
    _, headers = _contractor_auth(db_session, test_settings)

    worker = create_worker(db_session, city="Bengaluru")
    grant_capability(db_session, worker_id=worker.worker.id, task_id=task.id, level=3)
    # Meets the level requirement, but holds no safety qualification yet.

    res = client.post(
        WORK_REQS,
        json={
            "city": "Bengaluru",
            "state": "Karnataka",
            "lines": [
                {
                    "taskId": task.id,
                    "minLevel": 3,
                    "quantity": 1,
                    "safetyQualificationRequired": True,
                }
            ],
        },
        headers=headers,
    )
    assert res.status_code == 201
    body = res.json()
    line = body["lines"][0]
    assert line["safetyQualificationRequired"] is True
    assert line["status"] == "ESCALATED"
    assert line["eligibleCount"] == 0

    # Grant the qualification and re-fetch (live recompute) — now eligible.
    grant_safety_qualification(db_session, worker_id=worker.worker.id, task_id=task.id)
    get_res = client.get(f"{WORK_REQS}/{body['id']}", headers=headers)
    assert get_res.status_code == 200
    line_after = get_res.json()["lines"][0]
    assert line_after["status"] == "FULFILLED"
    assert line_after["candidates"][0]["workerId"] == worker.worker.id


# ---------------------------------------------------------------------------
# Access control and input validation the above scenarios rely on.
# ---------------------------------------------------------------------------
def test_worker_role_is_forbidden_from_both_endpoints(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    worker = create_worker(db_session)
    worker_headers = auth_header(
        user_id=worker.user.id, role="WORKER", phone=worker.user.phone, settings=test_settings
    )

    post_res = client.post(
        WORK_REQS,
        json={"lines": [{"taskId": tasks["WIRING"].id, "minLevel": 1, "quantity": 1}]},
        headers=worker_headers,
    )
    assert post_res.status_code == 403

    get_res = client.get(f"{WORK_REQS}/00000000-0000-4000-8000-000000000000", headers=worker_headers)
    assert get_res.status_code == 403


def test_a_different_contractor_cannot_view_someone_elses_work_requirement(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    _, owner_headers = _contractor_auth(db_session, test_settings)
    _, other_headers = _contractor_auth(db_session, test_settings)

    create_res = client.post(
        WORK_REQS,
        json={"lines": [{"taskId": tasks["WIRING"].id, "minLevel": 1, "quantity": 1}]},
        headers=owner_headers,
    )
    work_requirement_id = create_res.json()["id"]

    other_res = client.get(f"{WORK_REQS}/{work_requirement_id}", headers=other_headers)
    assert other_res.status_code == 403

    owner_res = client.get(f"{WORK_REQS}/{work_requirement_id}", headers=owner_headers)
    assert owner_res.status_code == 200


def test_admin_can_view_any_work_requirement(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    _, owner_headers = _contractor_auth(db_session, test_settings)
    admin_headers = auth_header(
        user_id="33333333-3333-4333-8333-333333333333",
        role="ADMIN",
        phone="+919990000099",
        settings=test_settings,
    )

    create_res = client.post(
        WORK_REQS,
        json={"lines": [{"taskId": tasks["WIRING"].id, "minLevel": 1, "quantity": 1}]},
        headers=owner_headers,
    )
    work_requirement_id = create_res.json()["id"]

    admin_res = client.get(f"{WORK_REQS}/{work_requirement_id}", headers=admin_headers)
    assert admin_res.status_code == 200


def test_get_404s_on_a_well_formed_but_nonexistent_id(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    seed_taxonomy(db_session)
    _, headers = _contractor_auth(db_session, test_settings)
    res = client.get(f"{WORK_REQS}/00000000-0000-4000-8000-000000000000", headers=headers)
    assert res.status_code == 404


def test_create_400s_with_no_lines(client: TestClient, db_session: Session, test_settings: Settings) -> None:
    seed_taxonomy(db_session)
    _, headers = _contractor_auth(db_session, test_settings)
    res = client.post(WORK_REQS, json={"lines": []}, headers=headers)
    assert res.status_code == 400


def test_create_400s_on_invalid_min_level_and_zero_quantity(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    _, headers = _contractor_auth(db_session, test_settings)

    bad_level = client.post(
        WORK_REQS,
        json={"lines": [{"taskId": tasks["WIRING"].id, "minLevel": 9, "quantity": 1}]},
        headers=headers,
    )
    assert bad_level.status_code == 400

    bad_quantity = client.post(
        WORK_REQS,
        json={"lines": [{"taskId": tasks["WIRING"].id, "minLevel": 1, "quantity": 0}]},
        headers=headers,
    )
    assert bad_quantity.status_code == 400


def test_create_404s_on_a_nonexistent_task_id(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    seed_taxonomy(db_session)
    _, headers = _contractor_auth(db_session, test_settings)
    res = client.post(
        WORK_REQS,
        json={
            "lines": [
                {"taskId": "00000000-0000-4000-8000-000000000000", "minLevel": 1, "quantity": 1}
            ]
        },
        headers=headers,
    )
    assert res.status_code == 404


def test_location_filter_excludes_a_worker_in_a_different_city(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["PIPE_INSTALLATION"]
    _, headers = _contractor_auth(db_session, test_settings)

    elsewhere = create_worker(db_session, city="Mumbai")
    grant_capability(db_session, worker_id=elsewhere.worker.id, task_id=task.id, level=2)

    res = client.post(
        WORK_REQS,
        json={
            "city": "Bengaluru",
            "lines": [{"taskId": task.id, "minLevel": 1, "quantity": 1}],
        },
        headers=headers,
    )
    line = res.json()["lines"][0]
    assert line["status"] == "ESCALATED"
    assert all(c["workerId"] != elsewhere.worker.id for c in line["eligibleWorkers"])


def test_unavailable_worker_is_excluded(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["LEAKAGE_REPAIR"]
    _, headers = _contractor_auth(db_session, test_settings)

    unavailable = create_worker(db_session, city="Bengaluru", is_available=False)
    grant_capability(db_session, worker_id=unavailable.worker.id, task_id=task.id, level=2)

    res = client.post(
        WORK_REQS,
        json={
            "city": "Bengaluru",
            "lines": [{"taskId": task.id, "minLevel": 1, "quantity": 1}],
        },
        headers=headers,
    )
    line = res.json()["lines"][0]
    assert line["status"] == "ESCALATED"
    assert all(c["workerId"] != unavailable.worker.id for c in line["eligibleWorkers"])
