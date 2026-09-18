"""
Authentication foundation only: token verification (`GET /api/auth/me`)
proves the JWT dependency chain end-to-end. This deliberately does NOT
implement the phone + OTP request/verify flow that issues tokens in the TS
backend (src/routes/auth.routes.ts) — that flow is product logic, not
foundation, and belongs in the next patch alongside whatever endpoints
actually need issuing. See docs/PythonMigration.md.
"""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_token
from app.infrastructure.security.jwt import TokenPayload

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def me(token: TokenPayload = Depends(get_current_token)) -> TokenPayload:
    return token
