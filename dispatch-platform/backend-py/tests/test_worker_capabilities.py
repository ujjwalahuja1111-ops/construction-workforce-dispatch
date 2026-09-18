"""
Worker Capability API (Self-Declaration) — Python port of the 12 contract
tests required by patch2-contract-v2.md §10 (backend/tests/worker-capability
.test.ts), in the same order they're listed there. Every request goes
through the real FastAPI app (`client` fixture -> TestClient(create_app())),
not the service layer directly, so these exercise the real routing/auth/
validation/error-handling chain — same discipline as the TS suite.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.enums import CapabilityProvenance
from app.infrastructure.db.models import AssessmentModel, TaskModel, WorkerCapabilityModel
from tests.factories import CreatedWorker, auth_header, create_worker, seed_taxonomy

CAPS = "/api/worker/capabilities"


def _worker_auth(
    db: Session, settings: Settings, *, skills: str | None = "MASON,HELPER"
) -> tuple[CreatedWorker, dict[str, str]]:
    created = create_worker(db, skills=skills)
    headers = auth_header(user_id=created.user.id, role="WORKER", phone=created.user.phone, settings=settings)
    return created, headers


# 1. 401 on both endpoints with no token.
def test_401s_on_both_endpoints_with_no_token(client: TestClient, db_session: Session) -> None:
    seed_taxonomy(db_session)

    post = client.post(CAPS, json={})
    assert post.status_code == 401

    get = client.get(CAPS)
    assert get.status_code == 401


# 2. 403 on both endpoints with a CONTRACTOR or ADMIN token.
def test_403s_on_both_endpoints_with_contractor_or_admin_token(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["WIRING"]

    contractor_auth = auth_header(
        user_id="11111111-1111-4111-8111-111111111111",
        role="CONTRACTOR",
        phone="+919990000001",
        settings=test_settings,
    )
    admin_auth = auth_header(
        user_id="22222222-2222-4222-8222-222222222222",
        role="ADMIN",
        phone="+919990000002",
        settings=test_settings,
    )

    for auth in (contractor_auth, admin_auth):
        post = client.post(CAPS, json={"taskId": task.id, "level": 2}, headers=auth)
        assert post.status_code == 403

        get = client.get(CAPS, headers=auth)
        assert get.status_code == 403


# 3. POST creates a new capability: provenance = SELF_DECLARED, 201, and
#    exactly one Assessment(type: SELF_DECLARATION) row exists afterward.
def test_creates_a_new_self_declared_capability(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    created, headers = _worker_auth(db_session, test_settings)
    task = tasks["BRICKWORK_NEW_WALL"]

    res = client.post(CAPS, json={"taskId": task.id, "level": 2}, headers=headers)

    assert res.status_code == 201
    body = res.json()["capability"]
    assert body["taskId"] == task.id
    assert body["level"] == 2
    assert body["provenance"] == "SELF_DECLARED"
    assert body["task"] == {
        "code": "BRICKWORK_NEW_WALL",
        "name": "Brickwork - New Wall",
        "tradeCode": "MASONRY",
    }
    assert "workerId" not in body

    capability = (
        db_session.query(WorkerCapabilityModel)
        .filter_by(worker_id=created.worker.id, task_id=task.id)
        .one()
    )
    assessments = db_session.query(AssessmentModel).filter_by(worker_capability_id=capability.id).all()
    assert len(assessments) == 1
    assert assessments[0].type == "SELF_DECLARATION"
    assert assessments[0].assessed_by is None


# 4. POST with level = 0, 5, -1, 2.5 -> 400, nothing written (no
#    WorkerCapability, no Assessment).
def test_rejects_out_of_range_levels_with_400_and_writes_nothing(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["BLOCKWORK"]

    for level in (0, 5, -1, 2.5):
        created, headers = _worker_auth(db_session, test_settings)

        res = client.post(CAPS, json={"taskId": task.id, "level": level}, headers=headers)
        assert res.status_code == 400

        capability = (
            db_session.query(WorkerCapabilityModel)
            .filter_by(worker_id=created.worker.id, task_id=task.id)
            .one_or_none()
        )
        assert capability is None


# 5. POST with a syntactically invalid taskId -> 400. With a well-formed but
#    nonexistent (or inactive) taskId -> 404.
def test_400s_on_a_syntactically_invalid_task_id(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    seed_taxonomy(db_session)
    _, headers = _worker_auth(db_session, test_settings)

    res = client.post(CAPS, json={"taskId": "not-a-uuid", "level": 1}, headers=headers)
    assert res.status_code == 400


def test_404s_on_a_well_formed_but_nonexistent_task_id(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    seed_taxonomy(db_session)
    _, headers = _worker_auth(db_session, test_settings)

    res = client.post(
        CAPS, json={"taskId": "00000000-0000-4000-8000-000000000000", "level": 1}, headers=headers
    )
    assert res.status_code == 404


def test_404s_on_a_well_formed_but_inactive_task_id(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    active_task = tasks["FAN_INSTALLATION"]
    _, headers = _worker_auth(db_session, test_settings)

    inactive_task = TaskModel(
        trade_id=active_task.trade_id,
        code="INACTIVE_TASK_TEST",
        name="Deactivated for test",
        is_active=False,
    )
    db_session.add(inactive_task)
    db_session.commit()

    res = client.post(CAPS, json={"taskId": inactive_task.id, "level": 1}, headers=headers)
    assert res.status_code == 404


# 6. POST twice for the same (worker, task) while still SELF_DECLARED:
#    second call -> 200, exactly one WorkerCapability row with the new
#    level, and exactly two Assessment rows in chronological order.
def test_updates_an_existing_self_declared_capability_in_place(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    created, headers = _worker_auth(db_session, test_settings)
    task = tasks["LIGHT_INSTALLATION"]

    first = client.post(CAPS, json={"taskId": task.id, "level": 1}, headers=headers)
    assert first.status_code == 201

    second = client.post(CAPS, json={"taskId": task.id, "level": 3}, headers=headers)
    assert second.status_code == 200
    assert second.json()["capability"]["level"] == 3
    assert second.json()["capability"]["id"] == first.json()["capability"]["id"]

    rows = (
        db_session.query(WorkerCapabilityModel)
        .filter_by(worker_id=created.worker.id, task_id=task.id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].level == 3

    assessments = (
        db_session.query(AssessmentModel)
        .filter_by(worker_capability_id=rows[0].id)
        .order_by(AssessmentModel.assessed_at.asc())
        .all()
    )
    assert len(assessments) == 2
    assert all(a.type == "SELF_DECLARATION" for a in assessments)
    assert "1 → 3" in assessments[1].result


# 7. POST against a (worker, task) whose capability was seeded directly
#    (bypassing this API) as ASSESSED/PRACTICALLY_VERIFIED/
#    PERFORMANCE_CONFIRMED -> 409; re-fetch confirms level/provenance are
#    byte-for-byte unchanged, and no new Assessment row was created.
def test_rejects_with_409_when_existing_capability_already_assessed(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    task = tasks["FAULT_FINDING"]

    for provenance in (
        CapabilityProvenance.ASSESSED,
        CapabilityProvenance.PRACTICALLY_VERIFIED,
        CapabilityProvenance.PERFORMANCE_CONFIRMED,
    ):
        created, headers = _worker_auth(db_session, test_settings)

        seeded = WorkerCapabilityModel(
            worker_id=created.worker.id, task_id=task.id, level=2, provenance=provenance.value
        )
        db_session.add(seeded)
        db_session.commit()

        res = client.post(CAPS, json={"taskId": task.id, "level": 4}, headers=headers)
        assert res.status_code == 409

        db_session.refresh(seeded)
        assert seeded.level == 2
        assert seeded.provenance == provenance.value

        assessments = db_session.query(AssessmentModel).filter_by(worker_capability_id=seeded.id).all()
        assert len(assessments) == 0


# 8. GET returns only the authenticated worker's own capabilities.
def test_get_only_returns_the_authenticated_workers_own_capabilities(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    worker_a, headers_a = _worker_auth(db_session, test_settings)
    worker_b, headers_b = _worker_auth(db_session, test_settings)
    task_a = tasks["PIPE_INSTALLATION"]
    task_b = tasks["BATHROOM_PLUMBING"]

    db_session.add(
        WorkerCapabilityModel(
            worker_id=worker_a.worker.id, task_id=task_a.id, level=2, provenance="SELF_DECLARED"
        )
    )
    db_session.add(
        WorkerCapabilityModel(
            worker_id=worker_b.worker.id, task_id=task_b.id, level=3, provenance="SELF_DECLARED"
        )
    )
    db_session.commit()

    res = client.get(CAPS, headers=headers_a)
    assert res.status_code == 200
    caps = res.json()["capabilities"]
    assert len(caps) == 1
    assert caps[0]["taskId"] == task_a.id
    assert not any(c["taskId"] == task_b.id for c in caps)

    res_b = client.get(CAPS, headers=headers_b)
    caps_b = res_b.json()["capabilities"]
    assert len(caps_b) == 1
    assert caps_b[0]["taskId"] == task_b.id


# 9. GET for a worker with zero capabilities -> 200, { capabilities: [] }.
def test_get_returns_200_with_empty_array_for_worker_with_zero_capabilities(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    seed_taxonomy(db_session)
    _, headers = _worker_auth(db_session, test_settings)

    res = client.get(CAPS, headers=headers)
    assert res.status_code == 200
    assert res.json() == {"capabilities": []}


# 10. Regression: this API never touches Worker.skills (the legacy
#     flat-skill column).
def test_does_not_touch_legacy_worker_skills_column(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    created, headers = _worker_auth(db_session, test_settings, skills="MASON,HELPER,WELDER")
    task = tasks["BRICKWORK_REPAIR"]

    res = client.post(CAPS, json={"taskId": task.id, "level": 2}, headers=headers)
    assert res.status_code == 201

    db_session.refresh(created.worker)
    assert created.worker.legacy_skills_csv == "MASON,HELPER,WELDER"


# 11. Regression: nothing this API ever writes sets confidence,
#     restrictions, or evidence_ref to anything other than the fresh-row
#     default (None).
def test_never_sets_confidence_restrictions_or_evidence_ref(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    created, headers = _worker_auth(db_session, test_settings)
    task = tasks["LEAKAGE_REPAIR"]

    client.post(CAPS, json={"taskId": task.id, "level": 1}, headers=headers)
    client.post(CAPS, json={"taskId": task.id, "level": 2}, headers=headers)

    row = (
        db_session.query(WorkerCapabilityModel)
        .filter_by(worker_id=created.worker.id, task_id=task.id)
        .one()
    )
    assert row.confidence is None
    assert row.restrictions is None
    assert row.evidence_ref is None


# 12. Regression: a request body containing an extra workerId or provenance
#     field is accepted (extra fields don't error) but has zero effect.
def test_accepts_but_ignores_extra_worker_id_and_provenance_fields(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    tasks = seed_taxonomy(db_session)
    created, headers = _worker_auth(db_session, test_settings)
    other, _ = _worker_auth(db_session, test_settings)
    task = tasks["WIRING"]

    res = client.post(
        CAPS,
        json={
            "taskId": task.id,
            "level": 3,
            "workerId": other.worker.id,
            "provenance": "PERFORMANCE_CONFIRMED",
        },
        headers=headers,
    )

    assert res.status_code == 201
    assert res.json()["capability"]["provenance"] == "SELF_DECLARED"

    mine = (
        db_session.query(WorkerCapabilityModel)
        .filter_by(worker_id=created.worker.id, task_id=task.id)
        .one_or_none()
    )
    assert mine is not None
    assert mine.provenance == "SELF_DECLARED"

    other_row = (
        db_session.query(WorkerCapabilityModel)
        .filter_by(worker_id=other.worker.id, task_id=task.id)
        .one_or_none()
    )
    assert other_row is None
