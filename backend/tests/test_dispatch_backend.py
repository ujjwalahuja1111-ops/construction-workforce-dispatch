"""
Backend tests for the Construction Workforce Dispatch Platform Phase-1 MVP.
Real backend is Node/Express at /app/dispatch-platform/backend (port 8002),
exposed via FastAPI proxy on port 8001 through the Emergent ingress.
"""
import os
import time
import math
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
if not BASE_URL:
    # fall back to reading frontend .env
    for line in open("/app/frontend/.env"):
        if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip()
            break
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL missing"
BASE_URL = BASE_URL.rstrip("/")

DEV_OTP = "123456"
PRIMARY_PHONE = "+919020001000"   # Rajesh Kumar
SECONDARY_PHONE = "+919020001001"  # Suresh Yadav


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(api, phone):
    r = api.post(f"{BASE_URL}/api/auth/otp/request", json={"phone": phone})
    assert r.status_code == 200, r.text
    body = r.json()
    r = api.post(
        f"{BASE_URL}/api/auth/otp/verify", json={"phone": phone, "code": DEV_OTP}
    )
    assert r.status_code == 200, r.text
    data = r.json()
    return data["token"], data.get("user"), body


@pytest.fixture(scope="session")
def primary_token(api):
    tok, _, _ = _login(api, PRIMARY_PHONE)
    return tok


@pytest.fixture(scope="session")
def secondary_token(api):
    tok, _, _ = _login(api, SECONDARY_PHONE)
    return tok


def _auth(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------- health ----------
def test_health(api):
    r = api.get(f"{BASE_URL}/api/health")
    assert r.status_code == 200
    j = r.json()
    assert j.get("status") == "ok"


# ---------- auth ----------
class TestAuth:
    def test_otp_request_returns_devotp(self, api):
        r = api.post(f"{BASE_URL}/api/auth/otp/request", json={"phone": PRIMARY_PHONE})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("devOtp") == DEV_OTP
        assert "userId" in j

    def test_otp_verify_success(self, api):
        r = api.post(
            f"{BASE_URL}/api/auth/otp/verify",
            json={"phone": PRIMARY_PHONE, "code": DEV_OTP},
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert "token" in j and isinstance(j["token"], str) and len(j["token"]) > 10
        assert j.get("user") is not None
        assert j.get("profileComplete") is True

    def test_otp_verify_wrong_code(self, api):
        api.post(f"{BASE_URL}/api/auth/otp/request", json={"phone": PRIMARY_PHONE})
        r = api.post(
            f"{BASE_URL}/api/auth/otp/verify",
            json={"phone": PRIMARY_PHONE, "code": "000000"},
        )
        assert r.status_code == 401, r.text


# ---------- worker /me ----------
class TestWorkerMe:
    def test_me(self, api, primary_token):
        r = api.get(f"{BASE_URL}/api/worker/me", headers=_auth(primary_token))
        assert r.status_code == 200, r.text
        j = r.json()
        assert "user" in j and "worker" in j
        w = j["worker"]
        assert "skills" in w
        assert "trustScore" in w
        assert "city" in w


# ---------- offers & dispatch ordering ----------
class TestOffers:
    def test_offers_returned_and_sorted(self, api, primary_token, secondary_token):
        # pick whichever worker has offers
        token_used = primary_token
        r = api.get(f"{BASE_URL}/api/worker/offers", headers=_auth(primary_token))
        assert r.status_code == 200, r.text
        offers = r.json().get("offers", [])
        if not offers:
            r = api.get(
                f"{BASE_URL}/api/worker/offers", headers=_auth(secondary_token)
            )
            assert r.status_code == 200, r.text
            offers = r.json().get("offers", [])
            token_used = secondary_token
        assert len(offers) >= 1, "No offers for either seeded worker"
        for o in offers:
            assert "job" in o
            assert "distanceKm" in o
            assert "score" in o
        scores = [o["score"] for o in offers]
        assert scores == sorted(scores, reverse=True), f"Not sorted desc: {scores}"
        # stash for downstream tests
        pytest.offers_token = token_used
        pytest.offers_list = offers


# ---------- accept + decline + shift lifecycle ----------
class TestShiftLifecycle:
    def test_full_lifecycle(self, api):
        """Accept one offer, run through the state machine to CLOSED."""
        token = getattr(pytest, "offers_token", None)
        offers = getattr(pytest, "offers_list", None)
        if not token or not offers:
            pytest.skip("no offers captured earlier")
        # pick two offers if possible so we can test decline separately
        offer = offers[0]
        h = _auth(token)

        # ACCEPT
        r = api.post(
            f"{BASE_URL}/api/jobs/offers/accept",
            headers=h,
            json={"offerId": offer["id"]},
        )
        assert r.status_code in (200, 201), r.text
        shift = r.json().get("shift") or r.json()
        assert shift.get("state") == "ACCEPTED"
        job_daily_wage = offer["job"]["dailyWage"]
        assert shift.get("wageAmount") == job_daily_wage
        shift_id = shift["id"]
        project = offer["job"]["project"]
        lat = project.get("latitude") or project.get("lat")
        lon = project.get("longitude") or project.get("lng") or project.get("lon")
        assert lat is not None and lon is not None, f"project coords missing: {project}"
        pytest.shift_id = shift_id
        pytest.shift_lat = lat
        pytest.shift_lon = lon

        # DECLINE another offer if we have at least 2
        if len(offers) >= 2:
            offer2 = offers[1]
            r = api.post(
                f"{BASE_URL}/api/jobs/offers/decline",
                headers=h,
                json={"offerId": offer2["id"]},
            )
            assert r.status_code in (200, 201), r.text
            body = r.json()
            # tolerate different shapes
            offer_body = body.get("offer", body)
            state = offer_body.get("state") or offer_body.get("status")
            assert state == "DECLINED", body

        # active shift
        r = api.get(f"{BASE_URL}/api/shifts/active", headers=h)
        assert r.status_code == 200, r.text

        # helper to POST a transition
        def transition(name, payload=None):
            r = api.post(
                f"{BASE_URL}/api/shifts/{shift_id}/{name}",
                headers=h,
                json=(payload or {}),
            )
            return r

        # geofence: check-in far away must fail 422
        r = transition("check-in", {"latitude": 0.0, "longitude": 0.0})
        assert r.status_code == 422, f"Expected 422 for far check-in, got {r.status_code} {r.text}"

        # Full lifecycle
        for step, payload in [
            ("travel", None),
            ("arrive", None),
            ("check-in", {"latitude": lat, "longitude": lon}),
            ("start-work", None),
            ("break", None),
            ("resume", None),
            ("complete", None),
            ("check-out", {"latitude": lat, "longitude": lon}),
            ("close", None),
        ]:
            r = transition(step, payload)
            assert r.status_code in (200, 201), f"{step} failed {r.status_code} {r.text}"

        # illegal transition (close again on CLOSED)
        r = transition("close", None)
        assert r.status_code == 422, f"Expected 422 illegal transition, got {r.status_code}"


# ---------- earnings ----------
class TestEarnings:
    def test_earnings(self, api, secondary_token):
        # Use secondary worker (Suresh) — already has a closed shift.
        r = api.get(f"{BASE_URL}/api/worker/earnings", headers=_auth(secondary_token))
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("total", "week", "month"):
            assert k in j, f"missing {k}"
            assert isinstance(j[k], (int, float))
        assert isinstance(j.get("shifts"), list)


# ---------- notifications ----------
class TestNotifications:
    def test_list_and_read_all(self, api, primary_token):
        h = _auth(primary_token)
        r = api.get(f"{BASE_URL}/api/notifications", headers=h)
        assert r.status_code == 200, r.text
        j = r.json()
        assert isinstance(j.get("notifications"), list)
        r = api.post(f"{BASE_URL}/api/notifications/read-all", headers=h)
        assert r.status_code in (200, 204), r.text


# ---------- trust score recompute ----------
class TestTrust:
    def test_trust_score_present(self, api, primary_token):
        r = api.get(f"{BASE_URL}/api/worker/me", headers=_auth(primary_token))
        assert r.status_code == 200
        w = r.json()["worker"]
        s = w["trustScore"]
        assert 0 <= s <= 100, f"trustScore out of range: {s}"
