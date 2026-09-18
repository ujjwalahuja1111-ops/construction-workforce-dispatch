from fastapi.testclient import TestClient

from app.config import Settings
from app.infrastructure.security.jwt import create_access_token, decode_access_token


def test_token_roundtrip(test_settings: Settings) -> None:
    token = create_access_token({"sub": "user-1", "role": "WORKER", "phone": "+919990000001"}, test_settings)
    decoded = decode_access_token(token, test_settings)
    assert decoded == {"sub": "user-1", "role": "WORKER", "phone": "+919990000001"}


def test_me_401_with_no_token(client: TestClient) -> None:
    res = client.get("/api/auth/me")
    assert res.status_code == 401


def test_me_401_with_garbage_token(client: TestClient) -> None:
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert res.status_code == 401


def test_me_200_with_valid_token(client: TestClient, test_settings: Settings) -> None:
    token = create_access_token({"sub": "user-1", "role": "WORKER", "phone": "+919990000001"}, test_settings)
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json() == {"sub": "user-1", "role": "WORKER", "phone": "+919990000001"}
