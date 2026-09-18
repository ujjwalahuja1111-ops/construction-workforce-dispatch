"""
Shared FastAPI dependencies: the DB session (re-exported from
infrastructure.db.session for a shorter import path in routes) and the
auth dependency, mirroring requireAuth/requireRole in the TS backend's
src/middleware/auth.ts.
"""

from __future__ import annotations

from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings
from app.infrastructure.db.session import get_db
from app.infrastructure.security.jwt import TokenPayload, decode_access_token

__all__ = ["get_db", "get_current_token", "require_role"]

_bearer = HTTPBearer(auto_error=False)


def get_current_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> TokenPayload:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        return decode_access_token(credentials.credentials, settings)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc


def require_role(*roles: str) -> Callable[[TokenPayload], TokenPayload]:
    def _check(token: TokenPayload = Depends(get_current_token)) -> TokenPayload:
        if token["role"] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted")
        return token

    return _check
