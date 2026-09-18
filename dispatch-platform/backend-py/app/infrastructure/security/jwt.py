"""
JWT issuing/verification, deliberately shaped to match the TypeScript
backend's src/utils/jwt.ts: same three claims (`sub`, `role`, `phone`), same
algorithm (HS256), same secret env var name (JWT_SECRET). If both services
are configured with the same JWT_SECRET during the migration window, a
token either one issues verifies on the other.

This module only encodes/decodes tokens — it does not implement the phone
+ OTP request/verify flow that issues them in the TS backend. That flow
(and any other business logic beyond "can I trust this bearer token") is
out of scope for this foundation patch; see docs/PythonMigration.md.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TypedDict

import jwt

from app.config import Settings


class TokenPayload(TypedDict):
    sub: str
    role: str
    phone: str


def create_access_token(payload: TokenPayload, settings: Settings) -> str:
    expire = datetime.now(UTC) + timedelta(days=settings.jwt_expires_in_days)
    to_encode: dict[str, object] = {**payload, "exp": expire}
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> TokenPayload:
    """Raises jwt.InvalidTokenError (or a subclass) on any failure — expired,
    bad signature, malformed. Callers translate that into a 401, mirroring
    requireAuth's catch-and-401 behavior in the TS backend."""
    decoded = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return TokenPayload(sub=decoded["sub"], role=decoded["role"], phone=decoded["phone"])
